#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────
# AutoSaham — DigitalOcean One-Click Deploy Script
# 
# Usage (run on a fresh Ubuntu 22.04/24.04 Droplet):
#   curl -sSL https://raw.githubusercontent.com/YOUR_USER/AutoProjectSaham/main/scripts/deploy_digitalocean.sh | bash
#
# Or manually:
#   git clone <repo> /opt/autosaham
#   cd /opt/autosaham
#   bash scripts/deploy_digitalocean.sh
#
# Prerequisites:
#   - Ubuntu 22.04/24.04 Droplet (minimum 4GB RAM)
#   - Root or sudo access
#   - Optional: domain name pointed to Droplet IP
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
echo "═══════════════════════════════════════════════════════"
echo ""

# ─── Step 1: System Update & Dependencies ───────────────
info "Step 1/7: Installing system dependencies..."

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
    jq

log "System packages installed"

# ─── Step 2: Install Docker ─────────────────────────────
info "Step 2/7: Installing Docker..."

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

# ─── Step 3: Clone / Update Repository ──────────────────
info "Step 3/7: Cloning repository..."

if [ -d "$APP_DIR/.git" ]; then
    cd "$APP_DIR"
    git pull origin main
    log "Repository updated"
else
    git clone "$REPO_URL" "$APP_DIR"
    cd "$APP_DIR"
    log "Repository cloned to $APP_DIR"
fi

# ─── Step 4: Generate .env ──────────────────────────────
info "Step 4/7: Generating environment configuration..."

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

    log ".env generated with secure passwords"
    warn "⚠ Edit .env to add your API keys: nano $APP_DIR/.env"
else
    log ".env already exists (keeping current)"
fi

# ─── Step 5: Configure Firewall ─────────────────────────
info "Step 5/7: Configuring firewall..."

ufw --force reset
ufw default deny incoming
ufw default allow outgoing
ufw allow ssh
ufw allow 80/tcp    # HTTP
ufw allow 443/tcp   # HTTPS
ufw --force enable
log "Firewall configured (SSH + HTTP + HTTPS)"

# ─── Step 6: Configure Fail2Ban ─────────────────────────
info "Step 6/7: Configuring fail2ban..."

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

# ─── Step 7: Build & Start Containers ───────────────────
info "Step 7/7: Building and starting containers..."

cd "$APP_DIR"
docker compose -f docker-compose.digitalocean.yml down 2>/dev/null || true
docker compose -f docker-compose.digitalocean.yml up -d --build

echo ""
echo "═══════════════════════════════════════════════════════"
echo "  ✅ Deployment Complete!"
echo "═══════════════════════════════════════════════════════"
echo ""
echo "  🌐 API Server:  http://$(curl -s ifconfig.me):8000"
echo "  🖥  Frontend:    http://$(curl -s ifconfig.me)"
echo "  📊 Health:      http://$(curl -s ifconfig.me)/nginx-health"
echo ""

# Wait for services to be ready
info "Waiting for services to start..."
sleep 15

# Check service status
docker compose -f docker-compose.digitalocean.yml ps

echo ""
echo "  📝 Next Steps:"
echo "  1. Edit API keys:    nano $APP_DIR/.env"
echo "  2. Restart services: cd $APP_DIR && docker compose -f docker-compose.digitalocean.yml restart"
echo "  3. Set up SSL:       bash scripts/setup_ssl.sh yourdomain.com"
echo "  4. View logs:        docker compose -f docker-compose.digitalocean.yml logs -f"
echo "  5. Monitor:          docker stats"
echo ""
echo "  💰 Estimated cost: ~\$24/month (s-2vcpu-4gb Droplet)"
echo "  🎓 Student Pack: \$200 credit = ~8 months free!"
echo ""