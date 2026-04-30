#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────
# AutoSaham — Let's Encrypt SSL Setup for DigitalOcean
#
# Usage:
#   bash scripts/setup_ssl.sh yourdomain.com [your@email.com]
#
# Prerequisites:
#   - Domain DNS A record pointing to this Droplet's IP
#   - Port 80 and 443 open in firewall
#   - Docker containers running
# ─────────────────────────────────────────────────────────────────

set -euo pipefail

DOMAIN="${1:-}"
EMAIL="${2:-}"
APP_DIR="/opt/autosaham"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log()  { echo -e "${GREEN}[✓]${NC} $1"; }
warn() { echo -e "${YELLOW}[!]${NC} $1"; }
err()  { echo -e "${RED}[✗]${NC} $1"; exit 1; }

if [ -z "$DOMAIN" ]; then
    echo "Usage: bash scripts/setup_ssl.sh <domain> [email]"
    echo "Example: bash scripts/setup_ssl.sh trading.yourdomain.com you@email.com"
    exit 1
fi

if [ -z "$EMAIL" ]; then
    EMAIL="admin@${DOMAIN}"
    warn "No email provided, using: ${EMAIL}"
fi

echo ""
echo "═══════════════════════════════════════════════════════"
echo "  🔒 SSL Setup for: ${DOMAIN}"
echo "═══════════════════════════════════════════════════════"
echo ""

# Step 1: Verify DNS
DROPLET_IP=$(curl -s ifconfig.me)
DNS_IP=$(dig +short "$DOMAIN" 2>/dev/null || nslookup "$DOMAIN" 2>/dev/null | grep -oP 'Address: \K[\d.]+' | tail -1)

if [ "$DROPLET_IP" != "$DNS_IP" ]; then
    warn "DNS might not be pointing to this Droplet yet."
    warn "  Droplet IP: ${DROPLET_IP}"
    warn "  DNS IP:     ${DNS_IP:-not resolved}"
    echo ""
    read -p "Continue anyway? (y/N): " -n 1 -r
    echo ""
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Step 2: Run certbot to get certificate
cd "$APP_DIR"

# Temporarily update nginx.conf for ACME challenge
docker compose -f docker-compose.digitalocean.yml run --rm certbot \
    certbot certonly \
    --webroot \
    --webroot-path=/var/www/certbot \
    --email "$EMAIL" \
    --agree-tos \
    --no-eff-email \
    -d "$DOMAIN" \
    --non-interactive

if [ $? -ne 0 ]; then
    # Try standalone if webroot fails
    warn "Webroot method failed, trying standalone..."
    docker compose -f docker-compose.digitalocean.yml stop nginx
    docker compose -f docker-compose.digitalocean.yml run --rm certbot \
        certbot certonly \
        --standalone \
        --email "$EMAIL" \
        --agree-tos \
        --no-eff-email \
        -d "$DOMAIN" \
        --non-interactive
    docker compose -f docker-compose.digitalocean.yml start nginx
fi

# Step 3: Update nginx.conf with SSL
log "Updating nginx.conf for HTTPS..."

# Create the SSL-enabled nginx.conf
cat > deploy/nginx.conf << NGINX_EOF
limit_req_zone \$binary_remote_addr zone=api_limit:10m rate=30r/s;

upstream api_backend {
    server api:8000;
    keepalive 32;
}

upstream frontend_backend {
    server frontend:80;
}

# HTTP → HTTPS redirect
server {
    listen 80;
    server_name ${DOMAIN};

    location /.well-known/acme-challenge/ {
        root /var/www/certbot;
    }

    location /nginx-health {
        access_log off;
        return 200 "ok";
        add_header Content-Type text/plain;
    }

    location / {
        return 301 https://\$host\$request_uri;
    }
}

# HTTPS server
server {
    listen 443 ssl http2;
    server_name ${DOMAIN};

    ssl_certificate /etc/letsencrypt/live/${DOMAIN}/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/${DOMAIN}/privkey.pem;

    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384;
    ssl_prefer_server_ciphers off;
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 1d;

    add_header Strict-Transport-Security "max-age=63072000; includeSubDomains; preload" always;
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;

    gzip on;
    gzip_vary on;
    gzip_min_length 1024;
    gzip_types text/plain text/css application/json application/javascript text/xml application/xml text/javascript image/svg+xml;

    location /api/ {
        limit_req zone=api_limit burst=50 nodelay;
        proxy_pass http://api_backend;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_read_timeout 300s;
        proxy_connect_timeout 10s;
    }

    location /ws {
        proxy_pass http://api_backend;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_read_timeout 86400s;
    }

    location / {
        proxy_pass http://frontend_backend;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
    }

    location /nginx-health {
        access_log off;
        return 200 "ok";
        add_header Content-Type text/plain;
    }
}
NGINX_EOF

# Step 4: Restart nginx to apply SSL
log "Restarting nginx with SSL configuration..."
docker compose -f docker-compose.digitalocean.yml restart nginx

echo ""
echo "═══════════════════════════════════════════════════════"
echo "  ✅ SSL Setup Complete!"
echo "═══════════════════════════════════════════════════════"
echo ""
echo "  🔒 HTTPS: https://${DOMAIN}"
echo "  📊 Health: https://${DOMAIN}/nginx-health"
echo ""
echo "  📝 SSL auto-renews every 12 hours via certbot container."
echo "  📝 To test renewal: docker compose -f docker-compose.digitalocean.yml run --rm certbot certbot renew --dry-run"
echo ""