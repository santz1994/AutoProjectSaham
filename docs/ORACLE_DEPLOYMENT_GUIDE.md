# 🚀 Oracle Cloud Free Tier — Complete Deployment Guide for AutoSaham

## Quick Start (3 Steps)

### Step 1: Generate SSH Key (if you don't have one)

Open PowerShell or Git Bash:

```bash
ssh-keygen -t ed25519 -C "autosaham" -f ~/.ssh/id_ed25519 -N ""
```

This creates:
- `~/.ssh/id_ed25519` (private key — keep secret)
- `~/.ssh/id_ed25519.pub` (public key — upload to Oracle)

---

### Step 2: Configure OCI CLI Authentication

#### Option A: Interactive Setup (Recommended)

```bash
oci setup config
```

You'll be prompted for:
1. **User OCID** — Go to OCI Console → Identity → Users → click your user → Copy OCID
2. **Tenancy OCID** — OCI Console → Administration → Tenancy Details → Copy OCID
3. **Region** — e.g., `ap-batam-1`, `ap-singapore-1`, `ap-tokyo-1`
4. **Generate new API Signing Key?** — Yes (press Enter)
5. **Key location** — Default is fine (`~/.oci/oci_api_key.pem`)
6. **Passphrase** — Leave empty for automation (just press Enter)

After setup, you need to upload the public key to OCI Console:
1. Go to OCI Console → Identity → Users → your user
2. Click "API Keys" in the left sidebar
3. Click "Add API Key"
4. Choose "Paste public key"
5. Paste content of `~/.oci/oci_api_key.pem.pub`
6. Click "Add"

#### Option B: Manual Config

Create file `~/.oci/config`:

```ini
[DEFAULT]
user=ocid1.tenancy.oc1..aaaaaaaaeouubkwytuezi65r26qjh25uyldz3egavw2rrijrevykewmmhpwa
fingerprint=aa:bb:cc:dd:ee:ff:00:11:22:33:44:55:66:77:88:99
tenancy=ocid1.tenancy.oc1..aaaaaaaaeouubkwytuezi65r26qjh25uyldz3egavw2rrijrevykewmmhpwa
region=ap-batam-1
key_file=~/.oci/oci_api_key.pem
```

Generate key manually:
```bash
openssl genrsa -out ~/.oci/oci_api_key.pem 2048
openssl rsa -pubout -in ~/.oci/oci_api_key.pem -out ~/.oci/oci_api_key.pem.pub
openssl md5 -c ~/.oci/oci_api_key.pem.pub | awk '{print $NF}'
# Use this fingerprint in config
```

---

### Step 3: Run Auto-Provisioning Script

#### Option A: Deploy AMD Micro Instance NOW (always available)

```bash
python scripts/oracle_auto_provision.py --mode micro
```

This creates a 1 OCPU / 1GB RAM instance immediately (good for testing/setup).
⚠️ NOT suitable for training or heavy workloads.

#### Option B: Deploy ARM Instance (4 OCPU / 24GB RAM)

```bash
python scripts/oracle_auto_provision.py --mode arm
```

This retries every 30-300 seconds with exponential backoff.
Best chance: 01:00-05:00 AM region time (when Oracle reclaims idle instances).

#### Option C: Deploy Both (Micro first for immediate access, ARM retries in background)

```bash
python scripts/oracle_auto_provision.py --mode both
```

#### Additional Options:

```bash
# Force start immediately (don't wait for optimal hours)
python scripts/oracle_auto_provision.py --mode arm --force

# Custom resources
python scripts/oracle_auto_provision.py --mode arm --ocpus 2 --memory 12

# With Discord webhook notification
# Edit CONFIG["webhook_url"] in the script first
python scripts/oracle_auto_provision.py --mode arm
```

---

## What the Script Does Automatically

1. ✅ Discovers all Availability Domains in your tenancy
2. ✅ Creates VCN (Virtual Cloud Network) if not exists
3. ✅ Creates Internet Gateway + Route Table
4. ✅ Opens firewall: SSH(22), HTTP(80), HTTPS(443), Frontend(3000), API(8000)
5. ✅ Creates Public Subnet
6. ✅ Finds latest Ubuntu 22.04 image for target architecture
7. ✅ Attempts instance creation, rotating through all ADs
8. ✅ On "Out of capacity": backs off with exponential delay + jitter
9. ✅ Logs everything to `oracle_provision.log`
10. ✅ Saves instance info to `oracle_instance_info.json` on success
11. ✅ Sends webhook notification on success (optional)

---

## After Instance is Created

### 1. Connect via SSH

```bash
# Get public IP from oracle_instance_info.json or OCI Console
ssh ubuntu@<PUBLIC_IP>
```

### 2. Deploy AutoSaham

```bash
# Clone and deploy
git clone https://github.com/santz1994/AutoProjectSaham.git
cd AutoProjectSaham
bash scripts/deploy_oracle_vps.sh
```

### 3. Edit Environment Variables

```bash
# Edit .env with your API keys
nano .env
```

Key variables:
```env
# Exchange API Keys (Read & Trade only, NO Withdrawal!)
BINANCE_API_KEY=your_key
BINANCE_API_SECRET=your_secret

# Optional: OpenAI for LLM features
OPENAI_API_KEY=your_key
```

### 4. Restart Services

```bash
cd ~/AutoProjectSaham
docker compose -f docker-compose.oracle.yml down
docker compose -f docker-compose.oracle.yml up -d --build
```

### 5. Verify Deployment

```bash
# Check all containers
docker compose -f docker-compose.oracle.yml ps

# Check API health
curl http://localhost:8000/api/v1/health

# Check frontend
curl http://localhost:3000/
```

---

## Can You Edit the Oracle Server with VS Code?

**YES!** Two methods:

### Method 1: VS Code Remote SSH (Recommended)

1. Install "Remote - SSH" extension in VS Code
2. Press `Ctrl+Shift+P` → "Remote-SSH: Connect to Host"
3. Enter: `ubuntu@<YOUR_ORACLE_IP>`
4. VS Code connects to the server — you can edit files, run terminal, debug, etc.
5. All changes are live on the server

### Method 2: Git Sync (Push from local → Pull on server)

```bash
# On local machine (your laptop)
git add . && git commit -m "update" && git push

# On Oracle server (via SSH or VS Code Remote)
cd ~/AutoProjectSaham
git pull
docker compose -f docker-compose.oracle.yml up -d --build
```

---

## Tips for Getting ARM Instance

1. **Best Time**: 01:00-05:00 AM region time (Oracle reclaims idle instances)
   - Singapore/Batam (UTC+8): Run script at 17:00-21:00 UTC
   - Tokyo (UTC+9): Run script at 16:00-20:00 UTC
   
2. **Keep Script Running**: Let it run overnight in a terminal/tmux/screen
   ```bash
   # Use tmux to keep running even if terminal closes
   tmux new -s oracle
   python scripts/oracle_auto_provision.py --mode arm
   # Detach: Ctrl+B, then D
   # Reattach: tmux attach -t oracle
   ```

3. **Multiple Regions**: If one region is full, try another:
   - `ap-batam-1` (Batam, Indonesia — closest to you)
   - `ap-singapore-1` (Singapore)
   - `ap-tokyo-1` (Tokyo)
   - `ap-mumbai-1` (Mumbai)
   
   Just change `CONFIG["region"]` in the script and run again.

4. **Use Micro First**: Deploy AMD Micro immediately for setup/testing
   ```bash
   python scripts/oracle_auto_provision.py --mode micro
   ```
   Then run ARM script in background for full-power instance.

---

## Architecture on Oracle

```
┌─────────────────────────────────────────────────┐
│  Oracle ARM Instance (24GB RAM)                 │
│                                                 │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐     │
│  │ PostgreSQL│  │  Redis   │  │   Nginx  │     │
│  │  (1GB)   │  │ (640MB)  │  │  (64MB)  │     │
│  └──────────┘  └──────────┘  └────┬─────┘     │
│                                    │            │
│  ┌──────────────────┐  ┌─────────┴─────────┐  │
│  │   API Server     │  │   Frontend        │  │
│  │  FastAPI (2GB)   │  │  React (512MB)    │  │
│  │  Port 8000       │  │  Port 3000        │  │
│  └──────────────────┘  └───────────────────┘  │
│                                                 │
│  Total: ~4.2GB / 24GB RAM                       │
└─────────────────────────────────────────────────┘
```

---

## Troubleshooting

### "OCI config not found"
Run `oci setup config` or create `~/.oci/config` manually (see Step 2).

### "Out of capacity" keeps failing
- Run script at 01:00-05:00 AM region time
- Try different region
- Use `--mode micro` for immediate AMD instance

### SSH connection refused
- Wait 2-3 minutes after instance creation for boot to complete
- Check OCI Console → Instances → your instance → check "Public IP"
- Ensure security list allows port 22

### Docker containers won't start
- Check RAM: `free -h` (ensure enough memory)
- Check logs: `docker compose -f docker-compose.oracle.yml logs`
- Reduce memory limits in `docker-compose.oracle.yml`