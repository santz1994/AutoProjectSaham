#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────
# AutoSaham — DigitalOcean One-Click Deploy Script
# Optimized for s-1vcpu-2gb ($12/mo) Singapore SGP1
#
# Usage (run on a fresh Ubuntu 24.04 Droplet):
#   ssh root@YOUR_DROPLET_IP
#   git clone https://github.com/santz1994/AutoProjectSaham.git /opt/autosaham
#   cd /opt/autosaham
#   bash scripts/deploy_digitalocean.sh
#
# This script:
#   1. Creates 2GB swap file (critical for low-RAM droplets)
#   2. Installs Docker & Docker Compose
#   3. Clones repo and generates .env
#   4. Configures firewall + fail2ban
#   5. Builds and starts all containers
# ─────────────────────────────────────────────────────────────────

set -euo pipefail

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log()   { echo -e "${GREEN}[✓]${NC} $1"; }
warn()  { echo -e "${YELLOW}[!]${NC} $1"; }
err()   { echo -e "${RED}[✗]${NC} $1"; exit 1; }
info()  { echo -e "${BLUE}[i]${NC} $1"; }

APP_DIR="/opt/autosaham"
REPO_URL="${REPO_URL:-https://github.com/santz1994/AutoProjectSaham.git}"

echo ""
echo "═══════════════════════════════════════════════════════"
echo "  🚀 AutoSaham — DigitalOcean Deployment Script"
echo "  Optimized for: s-1vcpu-2gb Singapore SGP1"
echo "═══════════════════════════════════════════════════════"
echo ""

# ─── Step 1: Swap File (critical for 2GB RAM) ────────────
info "Step 1/8: Setting up swap file (2GB)..."

if [ ! -f /swapfile ]; then
    fallocate -l 2G /swapfile
    chmod 600 /swapfile
    mkswap /swapfile
    swapon /swapfile
    echo '/swapfile none swap sw 0 0' >> /etc/fstab
    # Optimize swap usage
    sysctl vm.swappiness=10
    echo 'vm.swappiness=10' >> /etc/sysctl.conf
    sysctl vm.vfs_cache_pressure=50
    echo 'vm.vfs_cache_pressure=50' >> /etc/sysctl.conf
    log "2GB swap file created and active"
else
    log "Swap file already exists"
fi

# ─── Step 2: System Update & Dependencies ───────────────
info "Step 2/8: Installing system dependencies..."

export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq \
    apt-transport-https \
    ca-certificates \
    curl \
    gnupg \
    lsb-release \
    git \
    ufw \
    fail2ban \
    unattended-upgrades \
    jq \
    htop \
    ncdu

log "System packages installed"

# ─── Step 3: Install Docker ─────────────────────────────
info "Step 3/8: Installing Docker..."

if ! command -v docker &>/dev/null; then
    curl -fsSL https://get.docker.com | sh
    systemctl enable docker
    systemctl start docker
    log "Docker installed"
else
    log "Docker already installed ($(docker --version))"
fi

# Install Docker Compose plugin
if ! docker compose version &>/dev/null; then
    apt-get install -y -qq docker-compose-plugin
    log "Docker Compose plugin installed"
else
    log "Docker Compose already available ($(docker compose version --short))"
fi

# ─── Step 4: Clone / Update Repository ──────────────────
info "Step 4/8: Cloning repository..."

if [ -d "$APP_DIR/.git" ]; then
    cd "$APP_DIR"
    git pull origin master
    log "Repository updated"
else
    git clone -b master "$REPO_URL" "$APP_DIR"
    cd "$APP_DIR"
    log "Repository cloned to $APP_DIR"
fi

# ─── Step 5: Generate .env ──────────────────────────────
info "Step 5/8: Generating environment configuration..."

if [ ! -f .env ]; then
    # Generate secure passwords
    DB_PASS=$(openssl rand -hex 16)
    SECRET_KEY=$(openssl rand -hex 32)
    JWT_SECRET=$(openssl rand -hex 32)
    
    cat > .env << EOF
# ═══ AutoSaham Environment — Generated $(date -u +%Y-%m-%dT%H:%M:%SZ) ═══

# Database
POSTGRES_USER=autosaham
POSTGRES_PASSWORD=${DB_PASS}
DATABASE_URL=postgresql+asyncpg://autosaham:${DB_PASS}@postgres:5432/autosaham

# Redis
REDIS_URL=redis://redis:6379/0

# Security
SECRET_KEY=${SECRET_KEY}
JWT_SECRET=${JWT_SECRET}
ENVIRONMENT=production

# Exchange API Keys (ADD YOUR KEYS HERE)
BINANCE_API_KEY=
BINANCE_API_SECRET=
BYBIT_API_KEY=
BYBIT_API_SECRET=

# Trading Configuration
DEFAULT_EXCHANGE=binance
DEFAULT_SYMBOL=BTC/USDT
DEFAULT_TIMEFRAME=5m
MAX_LEVERAGE=5

# Notifications (optional)
SLACK_WEBHOOK_URL=
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=

# LLM Integration (optional)
OPENAI_API_KEY=
MIMO_API_KEY=
EOF

    chmod 600 .env
    log ".env generated with secure passwords"
    warn "⚠  Edit .env to add your API keys: nano $APP_DIR/.env"
else
    log ".env already exists (keeping current)"
fi

# ─── Step 6: Configure Firewall ─────────────────────────
info "Step 6/8: Configuring firewall..."

ufw --force reset
ufw default deny incoming
ufw default allow outgoing
ufw allow ssh
ufw allow 80/tcp    # HTTP
ufw allow 443/tcp   # HTTPS
ufw --force enable
log "Firewall configured (SSH + HTTP + HTTPS)"

# ─── Step 7: Configure Fail2Ban ─────────────────────────
info "Step 7/8: Configuring fail2ban..."

cat > /etc/fail2ban/jail.local << 'EOF'
[sshd]
enabled = true
port = ssh
filter = sshd
logpath = /var/log/auth.log
maxretry = 5
bantime = 3600
findtime = 600

[nginx-http-auth]
enabled = true
port = http,https
filter = nginx-http-auth
logpath = /var/log/nginx/error.log
maxretry = 5
bantime = 3600
EOF

systemctl restart fail2ban
log "Fail2Ban configured"

# ─── Step 8: Build & Start Containers ───────────────────
info "Step 8/8: Building and starting containers..."

cd "$APP_DIR"
docker compose -f docker-compose.digitalocean.yml down 2>/dev/null || true
# Always use --no-cache for first build or when Dockerfile changes
# (avoids stale cached layers missing system packages like git)
docker compose -f docker-compose.digitalocean.yml build --no-cache api
docker compose -f docker-compose.digitalocean.yml up -d

echo ""
echo "═══════════════════════════════════════════════════════"
echo "  ✅ Deployment Complete!"
echo "═══════════════════════════════════════════════════════"
echo ""

DROPLET_IP=$(curl -s ifconfig.me 2>/dev/null || echo "YOUR_DROPLET_IP")

echo "  🌐 API Server:  http://${DROPLET_IP}:8000"
echo "  🖥  Frontend:    http://${DROPLET_IP}"
echo "  📊 Health:      http://${DROPLET_IP}/nginx-health"
echo ""

# Wait for services to be ready
info "Waiting for services to start (30s)..."
sleep 30

# Check service status
docker compose -f docker-compose.digitalocean.yml ps

echo ""
echo "  📝 Next Steps:"
echo "  1. Edit API keys:    nano $APP_DIR/.env"
echo "  2. Restart services: cd $APP_DIR && docker compose -f docker-compose.digitalocean.yml restart"
echo "  3. Set up SSL:       bash scripts/setup_ssl.sh yourdomain.com your@email.com"
echo "  4. View logs:        docker compose -f docker-compose.digitalocean.yml logs -f"
echo "  5. Monitor:          docker stats"
echo ""
echo "  💰 Estimated cost: ~\$12/month (s-1vcpu-2gb Droplet)"
echo "  🎓 Student Pack: \$200 credit = ~16 months free!"
echo ""
echo "  💻 Edit code via VS Code Remote SSH:"
echo "     1. Install 'Remote - SSH' extension in VS Code"
echo "     2. Ctrl+Shift+P → 'Remote-SSH: Connect to Host'"
echo "     3. Enter: root@${DROPLET_IP}"
echo "     4. Open folder: /opt/autosaham"
echo "     5. Edit files → restart: docker compose -f docker-compose.digitalocean.yml restart"
echo ""