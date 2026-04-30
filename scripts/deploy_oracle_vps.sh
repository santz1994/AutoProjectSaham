#!/usr/bin/env bash
# ==============================================================================
# AutoSaham — Oracle Cloud Free Tier (ARM64) One-Click Deploy Script
# Run this script on a fresh Ubuntu 22.04 ARM64 instance.
# Usage: curl -sL https://raw.githubusercontent.com/santz1994/AutoProjectSaham/main/scripts/deploy_oracle_vps.sh | bash
# Or:    bash scripts/deploy_oracle_vps.sh
# ==============================================================================

set -euo pipefail

echo "═══════════════════════════════════════════════════════════════"
echo "  AutoSaham — Oracle Cloud Free Tier Deployment"
echo "  4 OCPU ARM · 24GB RAM · 200GB Storage"
echo "═══════════════════════════════════════════════════════════════"
echo ""

# ── Configuration ─────────────────────────────────────────────────────────────
REPO_URL="https://github.com/santz1994/AutoProjectSaham.git"
INSTALL_DIR="/opt/autosaham"
BRANCH="main"

# ── 1. System Update ──────────────────────────────────────────────────────────
echo "[1/7] Updating system packages..."
sudo apt-get update -qq
sudo apt-get upgrade -y -qq

# ── 2. Install Docker ─────────────────────────────────────────────────────────
echo "[2/7] Installing Docker..."
if ! command -v docker &> /dev/null; then
    # Docker official install script (supports ARM64)
    curl -fsSL https://get.docker.com -o /tmp/get-docker.sh
    sudo sh /tmp/get-docker.sh
    sudo usermod -aG docker "$USER"
    rm /tmp/get-docker.sh
    echo "  ✓ Docker installed"
else
    echo "  ✓ Docker already installed ($(docker --version))"
fi

# Ensure Docker Compose plugin is available
if ! docker compose version &> /dev/null; then
    sudo apt-get install -y -qq docker-compose-plugin
    echo "  ✓ Docker Compose plugin installed"
else
    echo "  ✓ Docker Compose already available ($(docker compose version --short))"
fi

# ── 3. Install system dependencies ───────────────────────────────────────────
echo "[3/7] Installing system dependencies..."
sudo apt-get install -y -qq git curl wget htop ufw

# ── 4. Clone repository ──────────────────────────────────────────────────────
echo "[4/7] Cloning AutoSaham repository..."
if [ -d "$INSTALL_DIR" ]; then
    echo "  Repository exists, pulling latest..."
    cd "$INSTALL_DIR"
    git pull origin "$BRANCH"
else
    sudo git clone --branch "$BRANCH" "$REPO_URL" "$INSTALL_DIR"
    sudo chown -R "$USER:$USER" "$INSTALL_DIR"
    cd "$INSTALL_DIR"
fi
echo "  ✓ Repository ready at $INSTALL_DIR"

# ── 5. Configure environment ─────────────────────────────────────────────────
echo "[5/7] Configuring environment..."
if [ ! -f .env ]; then
    cp .env.example .env

    # Generate random DB password
    DB_PASS=$(openssl rand -hex 16)
    sed -i "s/DB_PASSWORD=.*/DB_PASSWORD=${DB_PASS}/" .env

    # Generate random Grafana password
    GRAFANA_PASS=$(openssl rand -hex 12)
    sed -i "s/GRAFANA_PASSWORD=.*/GRAFANA_PASSWORD=${GRAFANA_PASS}/" .env

    echo ""
    echo "  ╔══════════════════════════════════════════════════════════╗"
    echo "  ║  IMPORTANT: Edit .env file to add your credentials!     ║"
    echo "  ║                                                         ║"
    echo "  ║  Required:                                              ║"
    echo "  ║  - STOCKBIT_API_KEY / STOCKBIT_SECRET                   ║"
    echo "  ║  - AJAIB_EMAIL / AJAIB_PASSWORD                         ║"
    echo "  ║  - INDOPREMIER_USERNAME / INDOPREMIER_PASSWORD          ║"
    echo "  ║                                                         ║"
    echo "  ║  Generated passwords:                                   ║"
    echo "  ║  - DB Password: ${DB_PASS}                              ║"
    echo "  ║  - Grafana Password: ${GRAFANA_PASS}                    ║"
    echo "  ╚══════════════════════════════════════════════════════════╝"
    echo ""
else
    echo "  ✓ .env already exists"
fi

# ── 6. Create necessary directories ──────────────────────────────────────────
echo "[6/7] Creating directories..."
mkdir -p logs data models/rl data/dataset

# ── 7. Configure firewall ────────────────────────────────────────────────────
echo "[7/7] Configuring firewall..."
sudo ufw allow 22/tcp    # SSH
sudo ufw allow 80/tcp    # HTTP (nginx)
sudo ufw allow 443/tcp   # HTTPS (future)
sudo ufw --force enable
echo "  ✓ Firewall configured (SSH + HTTP + HTTPS)"

# ── Build and start services ─────────────────────────────────────────────────
echo ""
echo "Building and starting services..."
echo "This may take 5-10 minutes on first run..."
echo ""

docker compose -f docker-compose.oracle.yml build --no-cache
docker compose -f docker-compose.oracle.yml up -d

echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "  ✅ AutoSaham deployed successfully!"
echo ""
echo "  Services:"
echo "  • Frontend:  http://$(curl -s ifconfig.me 2>/dev/null || echo 'YOUR_IP')"
echo "  • API:       http://$(curl -s ifconfig.me 2>/dev/null || echo 'YOUR_IP')/api/"
echo "  • Health:    http://$(curl -s ifconfig.me 2>/dev/null || echo 'YOUR_IP')/health"
echo ""
echo "  Management:"
echo "  • View logs:    docker compose -f docker-compose.oracle.yml logs -f"
echo "  • Restart:      docker compose -f docker-compose.oracle.yml restart"
echo "  • Stop:         docker compose -f docker-compose.oracle.yml down"
echo "  • Update:       cd $INSTALL_DIR && git pull && docker compose -f docker-compose.oracle.yml up -d --build"
echo ""
echo "  ⚠️  Don't forget to edit .env with your broker credentials!"
echo "═══════════════════════════════════════════════════════════════"