#!/bin/bash
# Oracle Cloud Free Tier — Auto-Retry Instance Creation
# Usage: bash scripts/oracle_retry_instance.sh
#
# This script retries Oracle instance creation until capacity is available.
# Configure the variables below before running.

# ============================================
# CONFIGURATION — EDIT THESE
# ============================================
# Get from: OCI Console > Identity > Compartments
COMPARTMENT_ID="ocid1.tenancy.oc1..aaaaaaaaeouubkwytuezi65r26qjh25uyldz3egavw2rrijrevykewmmhpwa"

# Get from: OCI Console > Compute > Instances > Create > check AD names
# Usually: "AD-1", "AD-2", or "AD-3" (try the one with capacity)
AVAILABILITY_DOMAIN="AD-1"

# Get from: OCI Console > Networking > Virtual Cloud Networks > Subnet
SUBNET_ID="ocid1.subnet.oc1..YOUR_SUBNET_OCID"

# Ubuntu 22.04 ARM image (region-specific)
# Find yours: OCI Console > Compute > Custom Images, or use OCI CLI:
#   oci compute image list --compartment-id $COMPARTMENT_ID --operating-system "Canonical Ubuntu" --shape VM.Standard.A1.Flex
IMAGE_ID="ocid1.image.oc1..YOUR_IMAGE_OCID"

# SSH public key (paste your full key)
SSH_KEY="ssh-rsa AAAA... your-key-here"

# Instance config
DISPLAY_NAME="AutoSaham-Server"
OCPU=1
MEMORY_GB=6
MAX_RETRIES=100
WAIT_SECONDS=60
# ============================================

echo "============================================"
echo " Oracle Cloud Auto-Retry Instance Creator"
echo "============================================"
echo ""
echo "Shape: VM.Standard.A1.Flex (${OCPU} OCPU, ${MEMORY_GB}GB RAM)"
echo "Availability Domain: ${AVAILABILITY_DOMAIN}"
echo "Max retries: ${MAX_RETRIES} (waiting ${WAIT_SECONDS}s between attempts)"
echo ""

for i in $(seq 1 $MAX_RETRIES); do
    echo "[Attempt $i/$MAX_RETRIES] $(date '+%Y-%m-%d %H:%M:%S') Creating instance..."
    
    RESULT=$(oci compute instance launch \
        --compartment-id "$COMPARTMENT_ID" \
        --availability-domain "$AVAILABILITY_DOMAIN" \
        --shape VM.Standard.A1.Flex \
        --shape-config "{\"ocpus\":${OCPU},\"memoryInGBs\":${MEMORY_GB}}" \
        --image-id "$IMAGE_ID" \
        --subnet-id "$SUBNET_ID" \
        --assign-public-ip true \
        --display-name "$DISPLAY_NAME" \
        --ssh-keys "$SSH_KEY" \
        --metadata '{"user_data":"'$(echo '#!/bin/bash
echo "AutoSaham instance provisioned!" > /tmp/provisioned.txt' | base64 -w0)'"}' \
        2>&1)
    
    # Check if success
    if echo "$RESULT" | grep -q '"lifecycle-state"'; then
        echo ""
        echo "============================================"
        echo " SUCCESS! Instance created!"
        echo "============================================"
        echo "$RESULT" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    print(f\"Instance ID: {data.get('id', 'N/A')}\")
    print(f\"Display Name: {data.get('display-name', 'N/A')}\")
    print(f\"State: {data.get('lifecycle-state', 'N/A')}\")
    ip = data.get('public-ip', 'N/A')
    print(f\"Public IP: {ip}\")
    print()
    print('Next steps:')
    print(f'  ssh ubuntu@{ip}')
    print(f'  bash scripts/deploy_oracle_vps.sh')
except:
    print('(Could not parse instance details)')
"
        exit 0
    fi
    
    # Check for out-of-capacity error
    if echo "$RESULT" | grep -qi "out of capacity\|capacity\|InternalError"; then
        echo "  -> Out of capacity. Waiting ${WAIT_SECONDS}s before retry..."
        
        # Try alternate ADs on every 5th attempt
        if [ $((i % 5)) -eq 0 ]; then
            if [ "$AVAILABILITY_DOMAIN" = "AD-1" ]; then
                AVAILABILITY_DOMAIN="AD-2"
            elif [ "$AVAILABILITY_DOMAIN" = "AD-2" ]; then
                AVAILABILITY_DOMAIN="AD-3"
            else
                AVAILABILITY_DOMAIN="AD-1"
            fi
            echo "  -> Switching to ${AVAILABILITY_DOMAIN}"
        fi
    else
        echo "  -> Unexpected error: $RESULT"
        echo "  -> Retrying..."
    fi
    
    sleep $WAIT_SECONDS
done

echo ""
echo "============================================"
echo " FAILED after $MAX_RETRIES attempts."
echo " Try manually in OCI Console, or try a"
echo " different region/shape."
echo "============================================"