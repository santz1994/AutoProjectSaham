# AutoSaham Deployment Guide

Dokumen ini adalah playbook deployment yang netral lingkungan.
Status fitur dan progres implementasi mengikuti `Progress.md`.

Last updated: 2026-04-14 (UTC+7)

## PM Execution Context (10 Expert Roles)

Deployment readiness dievaluasi lintas peran berikut:

- AI/ML + Algorithm: memastikan model/output signal stabil sebelum deployment lanjutan.
- Python + Programming + Backend: memastikan service modular, test hijau, dan runtime aman.
- API + Fullstack + App: memastikan kontrak endpoint stabil untuk UI.
- Architecture: memastikan dekomposisi file besar berjalan dan technical debt menurun.
- UI/UX: memastikan informasi signal/risk tetap terbaca dan konsisten di frontend.

Status saat ini: deployment untuk local/dev siap; deployment production penuh ditahan sampai fase RL sandbox dan training (fase 3-4) mencapai baseline stabil.

## Scope

Panduan ini mencakup:

- Menjalankan backend FastAPI secara lokal
- Menjalankan frontend React (Vite) secara lokal
- Menjalankan stack container via Docker Compose
- Health check dan smoke validation dasar

Dokumen ini tidak mengasumsikan server Anda sudah aktif.

## Prerequisites

- Windows/Linux/macOS
- Python 3.11+ (workspace saat ini menggunakan venv Python 3.13)
- Node.js 18+
- Docker Desktop (opsional, untuk mode container)

## Option A: Local Development (recommended untuk iterasi cepat)

### 1) Backend

```bash
# dari root repository
.venv\Scripts\python.exe run_local_server.py
```

Backend default:

- API: http://localhost:8000
- OpenAPI docs: http://localhost:8000/docs

### 2) Frontend

```bash
cd frontend
npm install
npm run dev
```

Frontend default:

- UI: http://localhost:5173

Catatan:

- Frontend development mode mengakses backend melalui konfigurasi API client.
- Untuk flow fullstack otomatis, Anda juga bisa pakai `RUN_FULLSTACK.ps1` atau `RUN_FULLSTACK.bat` dari root.

## Option B: Docker Compose (full stack)

```bash
docker compose down --remove-orphans
docker compose up -d --build
docker compose ps
```

Service utama dari `docker-compose.yml`:

- `api` (FastAPI): host `8001` -> container `8000`
- `kong` (gateway): host `80`/`443`
- `postgres`: host `5432`
- `redis`: host `6379`
- `prometheus`: host `9090`
- `grafana`: host `3000`
- `alertmanager`: host `9093`

### Logs cepat

```bash
docker compose logs -f api
docker compose logs -f kong
docker compose logs -f postgres
docker compose logs -f redis
```

## Health Checks

### Local mode

```bash
curl http://localhost:8000/health
curl http://localhost:8000/docs
```

### Docker mode

```bash
# direct ke service api host mapping
curl http://localhost:8001/health

# cek status container
 docker compose ps
```

## Smoke Validation

Validasi minimum setelah backend aktif:

```bash
# auth register
curl -X POST http://localhost:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username":"testuser","password":"TestPass123!","email":"test@example.com"}'

# endpoint portfolio
curl http://localhost:8000/api/portfolio
```

Untuk validasi test suite terarah:

```bash
.venv\Scripts\python.exe -m pytest tests/test_feature_store.py tests/test_feature_store_phase2.py -q
.venv\Scripts\python.exe -m pytest tests/test_labeler_multimodal.py tests/test_trainer_multimodal.py -q
```

## Security and Runtime Flags

Beberapa flag penting (lihat juga `README.md`):

- `AUTOSAHAM_ADMIN_GUARD_ENABLED`
- `AUTOSAHAM_CSRF_PROTECTION_ENABLED`
- `AUTOSAHAM_ROLE_GUARD_ENABLED`
- `AUTOSAHAM_KILL_SWITCH_REQUIRE_ADMIN`
- `AUTOSAHAM_KILL_SWITCH_REQUIRE_2FA`

Pastikan nilai env disesuaikan sebelum deployment produksi.

## Troubleshooting

### Backend gagal start

```bash
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
.venv\Scripts\python.exe run_local_server.py
```

### Frontend tidak bisa hit API

- Periksa konfigurasi `VITE_API_BASE_URL`
- Verifikasi backend aktif di port target
- Jika lewat Kong, verifikasi route di `kong/kong.yml`

### Docker build lama

- Ini normal karena dependency ML cukup besar
- Gunakan Option A saat development harian

## Deployment Checklist

- [ ] Environment variables produksi sudah dikonfigurasi
- [ ] Health endpoint merespons normal
- [ ] Auth flow dasar tervalidasi
- [ ] Endpoint kritikal (`/api/portfolio`, `/api/signals`, `/api/ai/projection/{symbol}`) tervalidasi
- [ ] Guard keamanan (admin/role/CSRF/2FA) diuji sesuai kebijakan
- [ ] Logging dan monitoring (Prometheus/Grafana) aktif
- [ ] Kill-switch drill dijalankan (lihat `docs/KILL_SWITCH_DRILL_RUNBOOK.md`)

## Phase-Gated Rollout

Sebelum produksi penuh, gunakan gate berikut:

- Gate Fase 1-2: harus hijau (sudah tercapai untuk scope saat ini).
- Gate Fase 3: wajib selesai (reward/slippage/leverage environment tervalidasi).
- Gate Fase 4: minimal satu siklus training panjang dengan checkpoint restore tervalidasi.
- Gate Fase 5: uji staging cloud + rollback drill + kill-switch drill wajib lulus.

Tanpa gate di atas, deployment sebaiknya dibatasi pada dev/staging dan paper/simulated execution.

## References

- `README.md`
- `Progress.md`
- `docker-compose.yml`
- `kong/kong.yml`
- `docs/CICD_DEPLOYMENT_GUIDE.md`
- `docs/KILL_SWITCH_DRILL_RUNBOOK.md`
