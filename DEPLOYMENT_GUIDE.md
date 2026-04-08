# DEPLOYMENT INSTRUCTIONS

**Status:** ✅ READY FOR PRODUCTION DEPLOYMENT

---

## Quick Start Deployment

### Option 1: Docker Deployment (Recommended)

```bash
# 1. Navigate to project directory
cd D:\Project\AutoSaham

# 2. Clean up (optional)
docker compose down --remove-orphans

# 3. Build and start all services
docker compose up -d --build

# 4. Verify services are running
docker compose ps

# 5. Check logs
docker compose logs api
```

### Option 2: Local Development (Without Docker)

```bash
# 1. Activate virtual environment
.\.venv\Scripts\Activate.ps1

# 2. Start backend
python -m src.api.server

# 3. In another terminal, start frontend
cd frontend
npm run dev

# 4. Application available at http://localhost:5173
```

---

## Health Checks

### Docker Deployment

```bash
# Check service status
docker compose ps

# View logs
docker compose logs -f api        # Backend
docker compose logs -f kong       # API Gateway
docker compose logs -f postgresql # Database
docker compose logs -f redis      # Cache

# Execute commands in container
docker compose exec api python -c "from src.api.auth import register_user; print('✓ Auth module working')"
```

### Endpoints to Test

```bash
# Test register endpoint
curl -X POST http://localhost:8001/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "username": "testuser",
    "password": "TestPass123!",
    "email": "test@example.com"
  }'

# Test login endpoint
curl -X POST http://localhost:8001/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "username": "testuser",
    "password": "TestPass123!"
  }'

# Test portfolio endpoint
curl http://localhost:8001/api/portfolio
```

---

## Troubleshooting

### Docker containers won't start

```bash
# Clean up everything
docker compose down -v --remove-orphans

# Rebuild images freshly
docker compose build --no-cache

# Try again
docker compose up -d
```

### Python dependency issues

```bash
# Clear Docker build cache
docker builder prune -a

# Rebuild
docker compose build --no-cache
```

### Port conflicts

Default ports in use:
- **Frontend:** 3000 (React) + 5173 (Vite dev)
- **API Gateway:** 8001 (Kong)
- **Backend:** 8000 (FastAPI internal)
- **PostgreSQL:** 5432
- **Redis:** 6379

If ports are in use, modify `docker-compose.yml` port mappings.

---

## Production Checklist

Before going live:

- [ ] Test user registration via UI
- [ ] Test login flow
- [ ] Test forgot password flow
- [ ] Verify portfolio endpoint returns data
- [ ] Check logs for errors
- [ ] Verify database connectivity
- [ ] Configure email service (optional)
- [ ] Set broker API credentials (if using real broker)
- [ ] Update CORS whitelist for production domain
- [ ] Enable monitoring/logging aggregation

---

## Rollback Instructions

```bash
# If deployment fails, roll back with:
docker compose down
docker compose up -d <previous-version>

# Or remove all and start fresh
docker system prune -a
docker compose up -d --build
```

---

## Performance Monitoring

### Inside Docker

```bash
# Check resource usage
docker stats

# View container logs with timestamps
docker compose logs --timestamps api

# Follow logs in real-time
docker compose logs -f
```

### Database Monitoring

```bash
# Connect to PostgreSQL
docker compose exec postgresql psql -U trading -d autosaham

# Check user table
SELECT * FROM users;

# Check connections
SELECT datname, usename, application_name FROM pg_stat_activity;
```

---

## Success Indicators

After deployment, verify:

- ✅ `docker compose ps` shows all services as "Up"
- ✅ No error messages in logs
- ✅ POST /auth/register returns 200 status
- ✅ GET /api/portfolio returns valid JSON
- ✅ Frontend loads at http://localhost:3000

---

## Support

For issues, check:

1. **PRODUCTION_SIGN_OFF.md** - Detailed test results
2. **PRODUCTION_READY.md** - Feature documentation
3. **docker-compose.yml** - Service definitions
4. **logs/** - Application logs

---

**Ready to deploy! 🚀**
