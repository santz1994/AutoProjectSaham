# CI/CD & Deployment Guide
# AutoSaham Trading Platform - Phase 3 Task 4

## Overview

This guide documents the complete CI/CD pipeline and deployment infrastructure for the AutoSaham trading platform. The system is production-ready with full Indonesia market compliance (Jakarta timezone, IDX/IHSG, IDR, BEI rules).

## CI/CD Workflow

### Pipeline Stages

```
┌──────────────┐
│  New Commit  │
└──────┬───────┘
       │
       ↓
┌──────────────────┐
│  Checkout Code   │
└──────┬───────────┘
       │
       ↓
┌──────────────────────────────────────┐
│  Parallel Jobs                       │
├──────────────────────────────────────┤
│  1. Unit & Integration Tests         │  ─→ Coverage: codecov
│  2. Code Quality (Lint, Type Check)  │  ─→ Pylint, MyPy, Black
│  3. Security Scanning (Bandit)       │  ─→ Vulnerability detection
│  4. Performance Benchmarks           │  ─→ Baseline metrics
└──────┬───────────────────────────────┘
       │
       ↓ (if all pass)
┌──────────────────────┐
│  Build Docker Image  │
└──────┬───────────────┘
       │
       ↓
┌──────────────────────┐
│  Push to Registry    │
└──────┬───────────────┘
       │
       ↓
┌──────────────────────┐
│  Slack Notification  │
└──────────────────────┘
```

### Files

**GitHub Actions Workflows:**
- `.github/workflows/ci-cd.yml` - Main CI/CD pipeline
  - Test job: Unit tests + integration tests + coverage
  - Code quality job: Linting, type checking, formatting
  - Security job: Bandit vulnerability scanning
  - Docker job: Build and push container images
  - Performance job: Run benchmarks and track metrics
  - Notify job: Send Slack notifications

### Local Development Setup

```bash
# 1. Clone repository
git clone https://github.com/santz1994/AutoProjectSaham.git
cd AutoProjectSaham

# 2. Copy environment template
cp .env.example .env
# Edit .env with your credentials

# 3. Create Python virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# 4. Install dependencies
pip install -r requirements.txt

# 5. Run tests locally
pytest tests/ -v --cov=src

# 6. Start Docker stack
docker-compose up -d

# 7. Access services
# API: http://localhost:8000
# Grafana: http://localhost:3000 (admin/your_password)
# Prometheus: http://localhost:9090
```

## Docker Stack

**Services:**

1. **PostgreSQL** (Port 5432)
   - Database for trade data, positions, orders
   - Volumes: postgres_data
   - Health checks enabled

2. **AutoSaham API** (Port 8000)
   - Python FastAPI server
   - Connects to all brokers and market data
   - Metrics endpoint: /metrics
   - Health check: /health

3. **Prometheus** (Port 9090)
   - Metrics collection and storage
   - 30-day retention
   - Scrapes targets every 15 seconds
   - Alert rule evaluation

4. **AlertManager** (Port 9093)
   - Alert routing and grouping
   - Slack webhook integration
   - Email alerts for critical issues
   - Inhibition rules to reduce noise

5. **Grafana** (Port 3000)
   - Dashboard visualization
   - Pre-configured datasources
   - 3 main dashboards: Trading, Broker, Strategy
   - API access for automation

6. **Node Exporter** (Port 9100)
   - System metrics collection
   - CPU, memory, disk, network

## Deployment

### Building Docker Image

```bash
# Build from Dockerfile
docker build -t autosaham:latest .

# Or use docker-compose
docker-compose build api
```

### Running with Docker Compose

```bash
# Start all services
docker-compose up -d

# View logs
docker-compose logs -f api

# Stop services
docker-compose down

# Clean up volumes
docker-compose down -v
```

### Environment Variables

See `.env.example` for complete list. Critical variables:

```
# Broker credentials
STOCKBIT_API_KEY=...
STOCKBIT_SECRET=...
AJAIB_EMAIL=...
AJAIB_PASSWORD=...
INDOPREMIER_USERNAME=...
INDOPREMIER_PASSWORD=...

# Market configuration
TZ=Asia/Jakarta
TRADING_SYMBOLS=BBCA.JK,BMRI.JK,TLKM.JK

# Alerts
SLACK_WEBHOOK_URL=...
GRAFANA_PASSWORD=...
```

### Kong Tiered Rate Limiting (Free/Basic/Pro)

Kong declarative config di [kong/kong.yml](kong/kong.yml) sekarang memisahkan policy rate limit berdasarkan header `X-Autosaham-Tier`:

- `free`: fallback/default policy
- `basic`: limits menengah
- `pro`: limits tertinggi

Route tiered tersedia untuk jalur:

- `/api` (generic API)
- `/api/signals`, `/api/ai/projection`, `/api/ai/logs` (AI inference)
- `/api/broker/connect`, `/api/broker/disconnect`, `/api/strategies`, `/api/trades` (execution)

Backend melakukan validasi `X-Autosaham-Tier` terhadap role sesi (`viewer->free`, `trader->basic`, `developer/admin->pro`) untuk mencegah spoofing tier. Frontend otomatis mengirim header ini dari cookie `autosaham_tier`.

## Monitoring & Alerts

### Prometheus Targets

```yaml
prometheus:9090       # Prometheus itself
api:8000/metrics      # AutoSaham API metrics
node_exporter:9100    # System metrics
alertmanager:9093     # Alert counting
```

### Alert Rules

Located in `monitoring/alert_rules.yml` (23 rules):

**Order Execution:**
- HighOrderRejectionRate (>10%)
- LongOrderProcessingTime (>60s)

**Broker Connectivity:**
- BrokerDisconnected (CRITICAL)
- HighBrokerErrorRate (>5%)

**Risk Management:**
- MarginCallWarning (<150% margin)
- LargeUnrealizedLoss (>5% loss)
- HighValueAtRisk (>10% VaR)

**Market Data:**
- MarketDataStale (>30s no update)
- NoTradesExecuted (>1h idle)

**Strategy:**
- StrategyLosingStreak (>70% loss rate)
- HighConcentration (>50% in one symbol)

**IDX Compliance:**
- InvalidIDXSymbolFormat (must be *.JK)
- InvalidLotSize (must be 100+ shares)
- OutOfTradingHours (09:30-16:00 WIB)
- ExcessiveMarginUtilization (>80%)

### Dashboard Access

**Grafana** (Port 3000)
- Default login: admin / (from GRAFANA_PASSWORD)
- 3 Pre-configured dashboards:
  1. **Trading Dashboard** - Orders, positions, execution
  2. **Broker Dashboard** - API connectivity, latency, errors
  3. **Strategy Dashboard** - P&L, win rate, Sharpe, drawdown

All dashboards:
- Use Prometheus as datasource
- Display metrics in real-time
- IDR currency formatting
- Jakarta timezone (WIB)

## Testing

### Unit Tests

```bash
# Run all tests
pytest tests/ -v

# Run specific test class
pytest tests/test_broker_implementations.py::TestBaseBrokerInterface -v

# Run with coverage
pytest tests/ --cov=src --cov-report=html
```

### Integration Tests

```bash
# Run integration tests only
pytest tests/integration/ -v

# Test with real BEI API (requires credentials)
pytest tests/test_idx_api.py -v -m "not live"
```

### Code Quality

```bash
# Format code
black src/ tests/ scripts/

# Check imports
isort --check-only src/

# Lint
flake8 src/ --max-line-length=100

# Type checking
mypy src/ --ignore-missing-imports
```

## Production Checklist

Before deploying to production:

- [ ] All tests passing (100%)
- [ ] Code coverage > 80%
- [ ] No security vulnerabilities (Bandit)
- [ ] Performance benchmarks acceptable
- [ ] Broker credentials secured (use AWS Secrets Manager)
- [ ] Database backups configured
- [ ] Monitoring dashboards configured
- [ ] Alert channels verified (Slack, Email)
- [ ] Load testing completed
- [ ] Disaster recovery plan documented
- [ ] Security audit completed
- [ ] BEI compliance verified

## Troubleshooting

**Docker compose fails to start:**
```bash
# Check logs
docker-compose logs

# Check port availability
netstat -an | grep 5432  # PostgreSQL
netstat -an | grep 8000  # API
netstat -an | grep 9090  # Prometheus
```

**API server not responding:**
```bash
# Check health
curl http://localhost:8000/health

# View logs
docker-compose logs -f api

# Check database connection
docker-compose exec api python -c "
import sqlalchemy
# Test connection here
"
```

**Prometheus not scraping metrics:**
```bash
# Check targets
curl http://localhost:9090/api/v1/targets

# View config
curl http://localhost:9090/api/v1/status/config
```

**Alerts not firing:**
```bash
# Check alert rules
curl http://localhost:9090/api/v1/rules

# Test AlertManager webhook
curl -X POST http://localhost:9093/api/v1/alerts \
  -H 'Content-Type: application/json' \
  -d '[{"labels":{"alertname":"Test"}}]'
```

## Next Steps (Phase 3 Task 5)

- Load testing with Locust
- Performance profiling
- Database query optimization
- Cache tuning
- Horizontal scaling strategy

---

**Status:** ✅ **COMPLETE**  
**Files Created:** 5 (CI/CD workflow, Docker config, monitoring configs)  
**Test Coverage:** All tests passing  
**Jakarta Timezone:** ✅ WIB (UTC+7) throughout  
**IDX Compliance:** ✅ All BEI rules enforced  
**Phase 3 Progress:** 4/5 (80%)
