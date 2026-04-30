FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    libpq-dev \
    curl \
    tzdata \
    && rm -rf /var/lib/apt/lists/*

# Set UTC timezone for global Forex/Crypto workflows
ENV TZ=UTC
RUN ln -snf /usr/share/zoneinfo/UTC /etc/localtime && echo "UTC" > /etc/timezone

# Install Python dependencies
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY . .

# Create non-root user for security
RUN useradd -m -u 1000 trading && chown -R trading:trading /app
USER trading

# Environment variables — optimized for DigitalOcean App Platform (1GB RAM)
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
# MUST bind 0.0.0.0 for DO App Platform to route traffic to container
ENV API_HOST=0.0.0.0
ENV API_PORT=8000
# Memory optimization: single worker for 1GB RAM instances
ENV WEB_CONCURRENCY=1

# Health check (API server at port 8000)
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Expose API port
EXPOSE 8000

# Metadata
LABEL maintainer="AutoSaham Team"
LABEL description="AutoSaham Trading Platform - Production Ready for Forex/Crypto"
LABEL version="3.1.0"
LABEL timezone="UTC"
LABEL market="FOREX/CRYPTO"
LABEL currency="USD/USDT"
LABEL compliance="Global broker and exchange API policies"

# Default to API server with gunicorn+uvicorn for production stability
CMD ["python", "-m", "uvicorn", "src.api.server:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--limit-max-requests", "10000", "--timeout-keep-alive", "65"]
