#!/usr/bin/env python3
"""
Oracle Cloud Free Tier — Smart Auto-Provisioning Script
=========================================================

Features:
- Auto-retry with exponential backoff
- Rotates through all Availability Domains automatically
- Logs every attempt to oracle_provision.log
- Supports both ARM (A1.Flex 24GB) and AMD Micro (E2.1.Micro 1GB)
- Best timing: runs between 01:00-05:00 region time (when Oracle reclaims idle instances)
- Creates VCN + Subnet automatically if they don't exist
- Sends optional webhook notification on success (Discord/Slack/Telegram)

Prerequisites:
    pip install oci

Usage:
    1. Run `oci setup config` to configure credentials (first time only)
    2. Edit CONFIG below with your values
    3. Run: python scripts/oracle_auto_provision.py --mode arm
       Or:  python scripts/oracle_auto_provision.py --mode micro  (for immediate AMD instance)

Author: AutoSaham IT AI Developer
Date: 2026-04-30
"""

import oci
import sys
import json
import time
import logging
import argparse
import os
from datetime import datetime, timezone
from pathlib import Path

# =============================================================================
# CONFIGURATION — EDIT THESE VALUES
# =============================================================================

CONFIG = {
    # Your tenancy OCID (find in OCI Console > Administration > Tenancy Details)
    "tenancy_ocid": "ocid1.tenancy.oc1..aaaaaaaaeouubkwytuezi65r26qjh25uyldz3egavw2rrijrevykewmmhpwa",

    # Compartment OCID (usually same as tenancy for root)
    "compartment_ocid": "ocid1.tenancy.oc1..aaaaaaaaeouubkwytuezi65r26qjh25uyldz3egavw2rrijrevykewmmhpwa",

    # Region identifier
    "region": "ap-batam-1",

    # VCN will be created with these settings
    "vcn_display_name": "autosaham-vcn",
    "vcn_cidr": "10.0.0.0/16",
    "subnet_display_name": "autosaham-public-subnet",
    "subnet_cidr": "10.0.0.0/24",

    # Instance settings
    "instance_display_name": "autosaham-server",

    # ARM Instance (A1.Flex) — Full power
    "arm_ocpus": 4,
    "arm_memory_gb": 24,

    # AMD Micro (E2.1.Micro) — Temporary fallback
    "micro_ocpus": 1,
    "micro_memory_gb": 1,

    # Common settings
    "boot_volume_gb": 200,
    "image_os": "Canonical Ubuntu",
    "image_version": "22.04",
    "image_arch": "aarch64",  # Use "x86_64" for AMD Micro

    # SSH public key file path
    "ssh_public_key_path": os.path.expanduser("~/.ssh/id_rsa.pub"),

    # Webhook URL for notifications (optional, leave empty to disable)
    # Discord: https://discord.com/api/webhooks/xxx/yyy
    # Slack: https://hooks.slack.com/services/xxx/yyy/zzz
    "webhook_url": "",

    # Retry settings
    "max_retries": 500,
    "initial_wait_seconds": 30,
    "max_wait_seconds": 300,
    "optimal_hour_start": 1,  # Region local time (01:00)
    "optimal_hour_end": 5,    # Region local time (05:00)
}

# =============================================================================
# LOGGING SETUP
# =============================================================================

LOG_FILE = Path(__file__).parent.parent / "oracle_provision.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("oracle-provision")

# =============================================================================
# OCI CLIENT SETUP
# =============================================================================

def get_oci_clients(region: str):
    """Initialize OCI clients with default config from ~/.oci/config."""
    try:
        config = oci.config.from_file()
        config["region"] = region
    except oci.exceptions.ConfigFileNotFound:
        logger.error(
            "OCI config not found. Run 'oci setup config' first.\n"
            "Or manually create ~/.oci/config with:\n"
            "[DEFAULT]\n"
            "user=ocid1.user.oc1..xxx\n"
            "fingerprint=xx:xx:xx:xx\n"
            "tenancy=ocid1.tenancy.oc1..xxx\n"
            "region=ap-batam-1\n"
            "key_file=~/.oci/oci_api_key.pem"
        )
        sys.exit(1)

    identity = oci.identity.IdentityClient(config)
    compute = oci.compute.ComputeClient(config)
    network = oci.core.VirtualNetworkClient(config)

    return config, identity, compute, network


# =============================================================================
# VCN + SUBNET MANAGEMENT
# =============================================================================

def ensure_vcn_and_subnet(network, compartment_id, cfg):
    """Create VCN + Public Internet Gateway + Public Subnet if not exists."""
    # Search for existing VCN
    vcns = network.list_vcns(
        compartment_id=compartment_id,
        display_name=cfg["vcn_display_name"],
    ).data

    if vcns:
        vcn = vcns[0]
        logger.info(f"VCN found: {vcn.display_name} ({vcn.id})")
    else:
        logger.info(f"Creating VCN: {cfg['vcn_display_name']}...")
        vcn = network.create_vcn(
            oci.core.models.CreateVcnDetails(
                compartment_id=compartment_id,
                display_name=cfg["vcn_display_name"],
                cidr_block=cfg["vcn_cidr"],
                dns_label="autosaham",
            )
        ).data
        # Wait for VCN to be available
        oci.wait_until(network, network.get_vcn(vcn.id), "lifecycle_state", "AVAILABLE")
        logger.info(f"VCN created: {vcn.id}")

        # Create Internet Gateway
        ig = network.create_internet_gateway(
            oci.core.models.CreateInternetGatewayDetails(
                compartment_id=compartment_id,
                vcn_id=vcn.id,
                display_name="autosaham-ig",
                is_enabled=True,
            )
        ).data
        logger.info(f"Internet Gateway created: {ig.id}")

        # Update route table to use IG
        default_route_table = network.get_route_table(vcn.default_route_table_id).data
        network.update_route_table(
            vcn.default_route_table_id,
            oci.core.models.UpdateRouteTableDetails(
                route_rules=[
                    oci.core.models.RouteRule(
                        destination="0.0.0.0/0",
                        destination_type="CIDR_BLOCK",
                        network_entity_id=ig.id,
                    )
                ]
            ),
        )
        logger.info("Route table updated with Internet Gateway")

        # Update default security list to allow SSH + HTTP + HTTPS
        default_sl = network.get_security_list(vcn.default_security_list_id).data
        network.update_security_list(
            vcn.default_security_list_id,
            oci.core.models.UpdateSecurityListDetails(
                ingress_security_rules=[
                    oci.core.models.IngressSecurityRule(
                        protocol="6",  # TCP
                        source="0.0.0.0/0",
                        tcp_options=oci.core.models.TcpOptions(destination_port_range=oci.core.models.PortRange(min=22, max=22)),
                    ),
                    oci.core.models.IngressSecurityRule(
                        protocol="6",
                        source="0.0.0.0/0",
                        tcp_options=oci.core.models.TcpOptions(destination_port_range=oci.core.models.PortRange(min=80, max=80)),
                    ),
                    oci.core.models.IngressSecurityRule(
                        protocol="6",
                        source="0.0.0.0/0",
                        tcp_options=oci.core.models.TcpOptions(destination_port_range=oci.core.models.PortRange(min=443, max=443)),
                    ),
                    oci.core.models.IngressSecurityRule(
                        protocol="6",
                        source="0.0.0.0/0",
                        tcp_options=oci.core.models.TcpOptions(destination_port_range=oci.core.models.PortRange(min=3000, max=3000)),
                    ),
                    oci.core.models.IngressSecurityRule(
                        protocol="6",
                        source="0.0.0.0/0",
                        tcp_options=oci.core.models.TcpOptions(destination_port_range=oci.core.models.PortRange(min=8000, max=8000)),
                    ),
                ],
                egress_security_rules=[
                    oci.core.models.EgressSecurityRule(
                        protocol="all",
                        destination="0.0.0.0/0",
                    )
                ],
            ),
        )
        logger.info("Security list updated: SSH(22), HTTP(80), HTTPS(443), Frontend(3000), API(8000)")

    # Search for existing subnet
    subnets = network.list_subnets(
        compartment_id=compartment_id,
        vcn_id=vcn.id,
        display_name=cfg["subnet_display_name"],
    ).data

    if subnets:
        subnet = subnets[0]
        logger.info(f"Subnet found: {subnet.display_name} ({subnet.id})")
    else:
        logger.info(f"Creating subnet: {cfg['subnet_display_name']}...")
        subnet = network.create_subnet(
            oci.core.models.CreateSubnetDetails(
                compartment_id=compartment_id,
                vcn_id=vcn.id,
                display_name=cfg["subnet_display_name"],
                cidr_block=cfg["subnet_cidr"],
                dns_label="pubsubnet",
                prohibit_public_ip_on_vnic=False,
            )
        ).data
        oci.wait_until(network, network.get_subnet(subnet.id), "lifecycle_state", "AVAILABLE")
        logger.info(f"Subnet created: {subnet.id}")

    return vcn.id, subnet.id


# =============================================================================
# IMAGE DISCOVERY
# =============================================================================

def find_image(compute, compartment_id, os_name, version, arch):
    """Find the latest Ubuntu image for the given architecture."""
    images = compute.list_images(
        compartment_id=compartment_id,
        operating_system=os_name,
        operating_system_version=f"{version} Minimal {arch}" if arch == "aarch64" else f"{version} Minimal",
        sort_by="TIMECREATED",
        sort_order="DESC",
        limit=5,
    ).data

    if not images:
        # Try broader search
        images = compute.list_images(
            compartment_id=compartment_id,
            operating_system=os_name,
            sort_by="TIMECREATED",
            sort_order="DESC",
            limit=20,
        ).data
        images = [i for i in images if version in i.display_name and arch in i.display_name]

    if images:
        logger.info(f"Image found: {images[0].display_name} ({images[0].id})")
        return images[0].id

    logger.error(f"No image found for {os_name} {version} {arch}")
    return None


# =============================================================================
# AVAILABILITY DISCOVERY
# =============================================================================

def get_availability_domains(identity, compartment_id):
    """Get all availability domains in the tenancy."""
    ads = identity.list_availability_domains(compartment_id).data
    logger.info(f"Found {len(ads)} Availability Domain(s): {[a.name for a in ads]}")
    return ads


# =============================================================================
# INSTANCE CREATION
# =============================================================================

def create_instance(
    compute,
    compartment_id,
    availability_domain_name,
    subnet_id,
    image_id,
    display_name,
    ocpus,
    memory_gb,
    boot_volume_gb,
    ssh_public_key,
    shape,
):
    """Attempt to create an instance. Returns (success, result)."""
    try:
        result = compute.launch_instance(
            oci.core.models.LaunchInstanceDetails(
                compartment_id=compartment_id,
                availability_domain=availability_domain_name,
                display_name=display_name,
                shape=shape,
                shape_config=oci.core.models.LaunchInstanceShapeConfigDetails(
                    ocpus=ocpus,
                    memory_in_gbs=memory_gb,
                ),
                source_details=oci.core.models.InstanceSourceViaImageDetails(
                    source_type="image",
                    image_id=image_id,
                    boot_volume_size_in_gbs=boot_volume_gb,
                ),
                create_vnic_details=oci.core.models.CreateVnicDetails(
                    subnet_id=subnet_id,
                    assign_public_ip=True,
                    display_name=f"{display_name}-vnic",
                ),
                metadata={
                    "ssh_authorized_keys": ssh_public_key,
                    "user_data": __import__("base64").b64encode(
                        b"#!/bin/bash\necho 'AutoSaham instance provisioned!' > /tmp/provisioned.txt"
                    ).decode(),
                },
                agent_config=oci.core.models.LaunchInstanceAgentConfigDetails(
                    is_monitoring_disabled=False,
                ),
            )
        ).data
        return True, result
    except oci.exceptions.ServiceError as e:
        if "Out of capacity" in str(e) or "capacity" in str(e).lower():
            return False, "Out of capacity"
        else:
            logger.error(f"ServiceError: {e.status} — {e.message}")
            return False, str(e.message)
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return False, str(e)


# =============================================================================
# WEBHOOK NOTIFICATION
# =============================================================================

def send_webhook_notification(webhook_url, title, message, success=True):
    """Send notification to Discord/Slack webhook."""
    if not webhook_url:
        return

    try:
        import urllib.request

        color = 0x00FF00 if success else 0xFF0000

        if "discord" in webhook_url:
            payload = json.dumps({
                "embeds": [{
                    "title": title,
                    "description": message,
                    "color": color,
                }]
            }).encode()
        elif "hooks.slack" in webhook_url:
            payload = json.dumps({
                "text": f"*{title}*\n{message}",
            }).encode()
        else:
            payload = json.dumps({"text": f"{title}\n{message}"}).encode()

        req = urllib.request.Request(
            webhook_url,
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        urllib.request.urlopen(req, timeout=10)
        logger.info("Webhook notification sent")
    except Exception as e:
        logger.warning(f"Webhook notification failed: {e}")


# =============================================================================
# MAIN PROVISIONING LOOP
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="Oracle Cloud Smart Auto-Provisioning")
    parser.add_argument(
        "--mode",
        choices=["arm", "micro", "both"],
        default="arm",
        help="Instance type: arm (A1.Flex 24GB), micro (E2.1.Micro 1GB), both (micro first, then arm)",
    )
    parser.add_argument(
        "--ocpus",
        type=float,
        default=None,
        help="Override OCPUs (default: 4 for arm, 1 for micro)",
    )
    parser.add_argument(
        "--memory",
        type=float,
        default=None,
        help="Override memory in GB (default: 24 for arm, 1 for micro)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Don't wait for optimal hours, start immediately",
    )
    args = parser.parse_args()

    cfg = CONFIG
    mode = args.mode

    # Resolve SSH key
    ssh_key_path = cfg["ssh_public_key_path"]
    if not os.path.exists(ssh_key_path):
        # Try common alternatives
        for alt_path in ["~/.ssh/id_ed25519.pub", "~/.ssh/id_rsa.pub"]:
            expanded = os.path.expanduser(alt_path)
            if os.path.exists(expanded):
                ssh_key_path = expanded
                break
        else:
            logger.error(f"SSH public key not found at {ssh_key_path}")
            logger.error("Generate one with: ssh-keygen -t ed25519")
            sys.exit(1)

    with open(ssh_key_path, "r") as f:
        ssh_public_key = f.read().strip()

    logger.info("=" * 60)
    logger.info(" Oracle Cloud Smart Auto-Provisioning")
    logger.info("=" * 60)
    logger.info(f"Mode: {mode}")
    logger.info(f"Region: {cfg['region']}")
    logger.info(f"Max retries: {cfg['max_retries']}")
    logger.info(f"SSH key: {ssh_key_path}")
    logger.info(f"Log file: {LOG_FILE}")
    logger.info("")

    # Initialize OCI clients
    config, identity, compute, network = get_oci_clients(cfg["region"])
    compartment_id = cfg["compartment_ocid"]

    # Discover availability domains
    ads = get_availability_domains(identity, compartment_id)
    if not ads:
        logger.error("No availability domains found!")
        sys.exit(1)

    # Ensure VCN + Subnet exist
    vcn_id, subnet_id = ensure_vcn_and_subnet(network, compartment_id, cfg)

    # Find images
    if mode in ("arm", "both"):
        arm_image_id = find_image(
            compute, compartment_id,
            cfg["image_os"], cfg["image_version"], "aarch64"
        )
        if not arm_image_id:
            logger.error("Cannot find ARM image!")
            sys.exit(1)

    if mode in ("micro", "both"):
        micro_image_id = find_image(
            compute, compartment_id,
            cfg["image_os"], cfg["image_version"], "x86_64"
        )
        if not micro_image_id:
            logger.warning("Cannot find x86_64 minimal image, trying generic...")
            micro_image_id = find_image(
                compute, compartment_id,
                cfg["image_os"], cfg["image_version"], "x86_64"
            )
            if not micro_image_id:
                logger.error("Cannot find AMD Micro image!")
                if mode == "micro":
                    sys.exit(1)

    # Determine instance parameters
    if mode == "arm":
        shape = "VM.Standard.A1.Flex"
        ocpus = args.ocpus or cfg["arm_ocpus"]
        memory_gb = args.memory or cfg["arm_memory_gb"]
        image_id = arm_image_id
    elif mode == "micro":
        shape = "VM.Standard.E2.1.Micro"
        ocpus = 1
        memory_gb = 1
        image_id = micro_image_id
    else:  # both
        # Start with micro, then try arm
        pass

    logger.info("")
    logger.info("Starting provisioning loop...")
    logger.info(f"Shape: {shape if mode != 'both' else 'E2.1.Micro first, then A1.Flex'}")
    logger.info("")

    wait_seconds = cfg["initial_wait_seconds"]
    attempts = 0

    for attempt in range(1, cfg["max_retries"] + 1):
        attempts = attempt
        now = datetime.now(timezone.utc)

        # Calculate region local time (approximate: UTC+8 for Singapore/Batam)
        region_hour = (now.hour + 8) % 24
        is_optimal_time = cfg["optimal_hour_start"] <= region_hour < cfg["optimal_hour_end"]

        # Show timing info
        if not args.force and not is_optimal_time:
            next_optimal_hours = []
            for h in range(cfg["optimal_hour_start"], cfg["optimal_hour_end"]):
                utc_hour = (h - 8) % 24
                next_optimal_hours.append(f"{h:02d}:00 region ({utc_hour:02d}:00 UTC)")
            logger.info(
                f"[Attempt {attempt}] {now.strftime('%H:%M:%S UTC')} "
                f"(Region: ~{region_hour:02d}:xx) — "
                f"Not optimal hours yet. Best times: {', '.join(next_optimal_hours)}"
            )
            # Still try, but less aggressively
            if attempt > 1:
                wait_seconds = min(wait_seconds * 1.5, cfg["max_wait_seconds"])
        else:
            logger.info(
                f"[Attempt {attempt}] {now.strftime('%H:%M:%S UTC')} "
                f"(Region: ~{region_hour:02d}:xx) — "
                f"{'⭐ OPTIMAL TIME!' if is_optimal_time else 'Force mode'}"
            )

        # Rotate through ADs
        if mode == "both" and attempt <= 10:
            # First 10 attempts: try Micro
            current_shape = "VM.Standard.E2.1.Micro"
            current_ocpus = 1
            current_memory = 1
            current_image = micro_image_id
        elif mode == "both":
            # After 10 attempts: switch to ARM
            current_shape = "VM.Standard.A1.Flex"
            current_ocpus = args.ocpus or cfg["arm_ocpus"]
            current_memory = args.memory or cfg["arm_memory_gb"]
            current_image = arm_image_id
        else:
            current_shape = shape
            current_ocpus = ocpus
            current_memory = memory_gb
            current_image = image_id

        for ad in ads:
            logger.info(f"  Trying AD: {ad.name}, Shape: {current_shape} ({current_ocpus} OCPU, {current_memory}GB)")

            success, result = create_instance(
                compute=compute,
                compartment_id=compartment_id,
                availability_domain_name=ad.name,
                subnet_id=subnet_id,
                image_id=current_image,
                display_name=f"{cfg['instance_display_name']}-{current_shape.split('.')[-1].lower()}",
                ocpus=current_ocpus,
                memory_gb=current_memory,
                boot_volume_gb=cfg["boot_volume_gb"],
                ssh_public_key=ssh_public_key,
                shape=current_shape,
            )

            if success:
                instance = result
                logger.info("")
                logger.info("=" * 60)
                logger.info(" 🎉 SUCCESS! Instance Created!")
                logger.info("=" * 60)
                logger.info(f"Instance ID:      {instance.id}")
                logger.info(f"Display Name:     {instance.display_name}")
                logger.info(f"Shape:            {instance.shape}")
                logger.info(f"State:            {instance.lifecycle_state}")
                logger.info(f"Availability Dom: {instance.availability_domain}")
                logger.info(f"Attempts:         {attempt}")

                # Get public IP
                vnic_attachments = compute.list_vnic_attachments(
                    compartment_id=compartment_id,
                    instance_id=instance.id,
                ).data

                public_ip = "Waiting for assignment..."
                if vnic_attachments:
                    try:
                        vnic = oci.core.VirtualNetworkClient(config).get_vnic(
                            vnic_attachments[0].vnic_id
                        ).data
                        public_ip = vnic.public_ip or "No public IP assigned"
                    except Exception:
                        pass

                logger.info(f"Public IP:        {public_ip}")
                logger.info("")
                logger.info("Next steps:")
                logger.info(f"  ssh ubuntu@{public_ip}")
                logger.info("  sudo apt update && sudo apt upgrade -y")
                logger.info("  git clone https://github.com/santz1994/AutoProjectSaham.git")
                logger.info("  cd AutoProjectSaham && bash scripts/deploy_oracle_vps.sh")
                logger.info("")

                # Save instance info
                instance_info = {
                    "instance_id": instance.id,
                    "display_name": instance.display_name,
                    "shape": instance.shape,
                    "public_ip": public_ip,
                    "availability_domain": instance.availability_domain,
                    "created_at": now.isoformat(),
                    "attempts": attempt,
                    "mode": mode,
                }
                info_file = Path(__file__).parent.parent / "oracle_instance_info.json"
                with open(info_file, "w") as f:
                    json.dump(instance_info, f, indent=2)
                logger.info(f"Instance info saved to: {info_file}")

                # Webhook notification
                send_webhook_notification(
                    cfg["webhook_url"],
                    "🚀 AutoSaham Server Created!",
                    f"**Instance:** {instance.display_name}\n"
                    f"**Shape:** {instance.shape}\n"
                    f"**IP:** {public_ip}\n"
                    f"**AD:** {instance.availability_domain}\n"
                    f"**Attempts:** {attempt}",
                    success=True,
                )

                return 0
            else:
                logger.info(f"    -> {result}")

        # Exponential backoff with jitter
        jitter = __import__("random").uniform(0.5, 1.5)
        actual_wait = int(wait_seconds * jitter)
        logger.info(f"  All ADs exhausted. Waiting {actual_wait}s before next round...")
        time.sleep(actual_wait)

        # Increase wait time (but cap it)
        wait_seconds = min(wait_seconds * 1.3, cfg["max_wait_seconds"])

    logger.error(f"Failed after {attempts} attempts.")
    send_webhook_notification(
        cfg["webhook_url"],
        "❌ AutoSaham Provisioning Failed",
        f"Failed after {attempts} attempts. Check log: {LOG_FILE}",
        success=False,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())