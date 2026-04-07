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

# Set Jakarta timezone (WIB: UTC+7) for Indonesia market compliance
ENV TZ=Asia/Jakarta
RUN ln -snf /usr/share/zoneinfo/Asia/Jakarta /etc/localtime && echo "Asia/Jakarta" > /etc/timezone

# Install Python dependencies
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY . .

# Create non-root user for security
RUN useradd -m -u 1000 trading && chown -R trading:trading /app
USER trading

# Environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Health check (API server at port 8000)
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Expose API port
EXPOSE 8000

# Metadata
LABEL maintainer="AutoSaham Team"
LABEL description="AutoSaham Trading Platform - Production Ready with Indonesia Market Compliance"
LABEL version="3.0.0"
LABEL timezone="Asia/Jakarta (WIB: UTC+7)"
LABEL market="IDX/IHSG"
LABEL currency="IDR"
LABEL compliance="OJK, BEI, Indonesian Tax"

# Default to API server
CMD ["python", "-m", "src.api.server"]
