# 🚀 AutoSaham — DigitalOcean Deployment Guide

Complete guide to deploy the AutoSaham autonomous trading bot on DigitalOcean.

---

## Prerequisites

- **GitHub Student Developer Pack** ($200 credit → ~8 months free)
- Domain name (optional, but recommended for SSL)
- Binance/Bybit API keys (Read + Trade only, NO Withdrawal permission)

---

## Option A: App Platform (Easiest — ~$12-24/month)

### Step 1: Push code to GitHub
```bash
git add -A
git commit -m "ready for deployment"
git push origin main
```

### Step 2: Create App on DigitalOcean
1. Go to https://cloud.digitalocean.com/apps
2. Click **"Create App"**
3. Connect your GitHub repo: `santz1994/AutoProjectSaham`
4. DigitalOcean auto-detects `docker-compose.digitalocean.yml`
5. Configure environment variables (from `.env`):
   - `POSTGRES_PASSWORD` → generate a secure password
   - `SECRET_KEY` → generate a secure key
   - `BINANCE_API_KEY` → your Binance API key
   - `BINANCE_API_SECRET` → your Binance API secret
6. Choose plan: **Basic ($12/mo)** or **Professional ($24/mo)**
7. Click **"Create Resources"**

### Step 3: Access your app
- API: `https://your-app.ondigitalocean.app`
- Frontend: Same URL, served via nginx

### Limitations
- No direct SSH access (use DigitalOcean console)
- No persistent volume (use managed database for production)
- Cold starts on basic tier

---

## Option B: Droplet (Recommended — ~$24/month + full control)

### Step 1: Get a Droplet

#### Using Student Pack ($200 credit):
1. Go to https://www.digitalocean.com/github-students
2. Verify student status with GitHub
3. Get $200 credit (60-day expiry from activation)
4. Create Droplet:
   - **Image**: Ubuntu 24.04 LTS
   - **Plan**: Basic — Regular (Disk: SSD) → **s-2vcpu-4gb** ($24/mo)
   - **Region**: Singapore (SGP1) — closest to Indonesia
   - **Authentication**: SSH Key (recommended) or Password

### Step 2: Connect to Droplet
```bash
ssh root@YOUR_DROPLET_IP
```

### Step 3: One-Click Deploy
```bash
# Clone and deploy in one command
git clone -b master https://github.com/santz1994/AutoProjectSaham.git /opt/autosaham
cd /opt/autosaham
bash scripts/deploy_digitalocean.sh
```

The script automatically:
- Installs Docker & Docker Compose
- Configures firewall (SSH + HTTP + HTTPS)
- Sets up fail2ban for SSH protection
- Generates secure `.env` with random passwords
- Builds and starts all containers

### Step 4: Configure API Keys
```bash
nano /opt/autosaham/.env
# Add your Binance/Bybit API keys
# Save: Ctrl+O, Enter, Ctrl+X

# Restart to apply
cd /opt/autosaham
docker compose -f docker-compose.digitalocean.yml restart
```

### Step 5: Set Up SSL (Optional, recommended)
```bash
# Point your domain DNS A record to Droplet IP first!
bash /opt/autosaham/scripts/setup_ssl.sh yourdomain.com your@email.com
```

---

## Option C: Droplet + Managed Database (~$38/month)

For production reliability, use DigitalOcean Managed PostgreSQL:

1. Create Managed Database: https://cloud.digitalocean.com/databases
   - Engine: PostgreSQL 16
   - Plan: Basic — $15/month (1GB RAM, 10GB disk)
   - Region: Same as Droplet
2. Update `.env`:
   ```
   DATABASE_URL=postgresql+asyncpg://username:password@db-host:25060/autosaham?sslmode=require
   ```
3. Run migrations:
   ```bash
   cd /opt/autosaham
   docker compose -f docker-compose.digitalocean.yml restart api
   ```

---

## Editing Code on the Server

### Option 1: SSH + Nano/Vim (Quick edits)
```bash
ssh root@YOUR_DROPLET_IP
nano /opt/autosaham/src/api/server.py
docker compose -f docker-compose.digitalocean.yml restart api
```

### Option 2: VS Code Remote SSH (Recommended)
1. Install **"Remote - SSH"** extension in VS Code
2. `Ctrl+Shift+P` → "Remote-SSH: Connect to Host"
3. Enter: `root@YOUR_DROPLET_IP`
4. Open folder: `/opt/autosaham`
5. Edit files directly with full VS Code features (IntelliSense, debugging, etc.)
6. After editing, restart containers:
   ```bash
   cd /opt/autosaham && docker compose -f docker-compose.digitalocean.yml restart
   ```

### Option 3: GitHub Workflow (Best practice)
```bash
# Local machine: make changes, test, push
git add -A
git commit -m "feature: ..."
git push origin main

# Server: pull and restart
ssh root@DROPLET_IP "cd /opt/autosaham && git pull && docker compose -f docker-compose.digitalocean.yml up -d --build"
```

### Option 4: Port Forward (Edit .env, configs)
```bash
# From local machine, mount remote filesystem
code --remote ssh-remote+root@DROPLET_IP /opt/autosaham
```

---

## Useful Commands

```bash
# View all service status
docker compose -f docker-compose.digitalocean.yml ps

# View logs (follow)
docker compose -f docker-compose.digitalocean.yml logs -f api
docker compose -f docker-compose.digitalocean.yml logs -f nginx

# Restart a single service
docker compose -f docker-compose.digitalocean.yml restart api

# Rebuild after code changes
docker compose -f docker-compose.digitalocean.yml up -d --build

# Stop everything
docker compose -f docker-compose.digitalocean.yml down

# Database backup
docker exec autosaham-postgres pg_dump -U autosaham autosaham > backup_$(date +%Y%m%d).sql

# Monitor resources
docker stats

# Check disk usage
df -h
docker system df
```

---

## Cost Breakdown

| Component | Student Pack | Standard |
|-----------|-------------|----------|
| Droplet (s-2vcpu-4gb) | $0 (credit) | $24/mo |
| Managed DB (optional) | $0 (credit) | $15/mo |
| Domain (.com) | ~$12/year | ~$12/year |
| SSL (Let's Encrypt) | FREE | FREE |
| **Total** | **$0 for ~8 months** | **$24-39/mo** |

---

## Monitoring & Alerts

### Built-in Health Checks
- `http://YOUR_DROPLET_IP/nginx-health` → nginx status
- `http://YOUR_DROPLET_IP:8000/health` → API status

### Optional: UptimeRobot (Free)
1. Sign up at https://uptimerobot.com
2. Add HTTP monitor: `http://YOUR_DROPLET_IP/nginx-health`
3. Get email/Slack alerts if server goes down

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Container won't start | `docker compose logs api` to check errors |
| Database connection refused | Check postgres container: `docker compose ps` |
| Out of disk space | `docker system prune -a` to clean up |
| SSL cert expired | `bash scripts/setup_ssl.sh yourdomain.com` |
| Can't connect to exchange | Check API keys in `.env`, verify IP whitelist |
| Frontend shows old version | `docker compose up -d --build frontend` |

---

## Security Checklist

- [ ] SSH key authentication (disable password login)
- [ ] Firewall enabled (UFW: SSH + HTTP + HTTPS only)
- [ ] Fail2ban active
- [ ] Exchange API keys have **NO withdrawal permission**
- [ ] `.env` file permissions: `chmod 600 .env`
- [ ] SSL/TLS configured (HTTPS only)
- [ ] Regular backups configured
- [ ] Uptime monitoring active