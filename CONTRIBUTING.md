# Contributing to AutoSaham

Dokumen ini menjelaskan standar kontribusi untuk menjaga keamanan, kualitas, dan kestabilan platform.

## 1. Branching

- Gunakan branch feature/fix terpisah dari master.
- Nama branch disarankan:
  - feat/<short-topic>
  - fix/<short-topic>
  - chore/<short-topic>
  - refactor/<short-topic>
  - docs/<short-topic>

## 2. Commit Message

Gunakan format ringkas dan konsisten:

- feat: untuk fitur baru
- fix: untuk bug fix
- chore: untuk perubahan non-fungsional (CI, tooling, docs)
- refactor: untuk refactor tanpa perubahan perilaku
- test: untuk perubahan test
- docs: untuk dokumentasi

Contoh:
- feat(api): add kill switch endpoints
- chore(git): harden runtime-sensitive data ignore patterns
- fix(rl): correct ADWIN drift detection API usage
- refactor(api): extract frontend_routes helpers to service modules

## 3. Security Rules (Wajib)

- Jangan commit secret: API key, token, private key, kredensial broker.
- Gunakan env var untuk konfigurasi sensitif.
- Gunakan mekanisme state store terenkripsi untuk data sensitif runtime.
- Untuk endpoint trading sensitif, prioritaskan server-side validation.
- Pastikan `.env` dan data sensitif runtime ada di `.gitignore`.

## 4. Local Validation

Jalankan validasi minimum sebelum PR:

**Backend:**
```bash
python -m pytest tests/ -q
```

**Frontend:**
```bash
cd frontend
npm run type-check
npm run build
```

**Linting (opsional):**
```bash
flake8 src/
mypy src/ --config-file mypy.strict.ini
```

Jika perubahan menyentuh area tertentu, jalankan test targeted terkait area tersebut. Contoh:

```bash
# RL & Environment changes
python -m pytest tests/test_trading_env_fase3.py tests/test_rl_integration.py -q

# API changes
python -m pytest tests/test_frontend_signals.py tests/test_api_server.py -q

# ML / Online Learning changes
python -m pytest tests/test_online_learner.py tests/test_advanced_modules.py -q

# Ghost Machine / Execution changes
python -m pytest tests/test_advanced_modules.py -q
```

## 5. File Size Guidelines

Arsitektur AutoSaham mengikuti prinsip Single Responsibility Principle. Batas file yang sehat:

| Kategori | Batas Baris | Aksi |
|----------|-------------|------|
| Route/API handler | ≤ 300 | Thin wrapper — delegasikan ke service |
| Service module | ≤ 500 | Satu domain bisnis |
| ML/RL model | ≤ 500 | Pecah ke modul helper jika lebih |
| Test file | ≤ 400 | Fokus pada satu area pengujian |
| Config/Constants | ≤ 200 | Data statis saja |

File yang melebihi batas ini harus di-decompose secara bertahap ke modul yang lebih kecil. Pola yang digunakan:
- `src/api/services/*` — Business logic extraction dari frontend_routes.py
- `src/ml/feature_store_modules/*` — Domain-specific feature calculation
- `src/api/schemas/*` — Pydantic models
- `src/api/config/*` — Constants dan configuration

## 6. CI and Quality Expectations

- CI harus hijau pada workflow utama.
- Hindari menurunkan kualitas lint/type-check tanpa alasan yang jelas.
- Untuk perubahan keamanan, sertakan catatan threat/risk singkat pada PR.
- Test suite harus tetap hijau: target **80/80 PASS**.

## 7. Docs Update Policy

Perubahan arsitektur atau flow penting harus diikuti update dokumen:

- **README.md** — setup, usage, dan status tingkat tinggi
- **Progress.md** — checklist fase, wave, dan rekomendasi tindak lanjut
- **docs/** — panduan teknis mendalam (deployment, runbook)
- **CONTRIBUTING.md** — aturan kontribusi
- **LICENSE.md** — catatan lisensi dan dependency pihak ketiga

## 8. Review Guidelines

Dalam PR, sertakan:

- Ringkasan perubahan
- Dampak dan risiko
- Cara verifikasi (test command)
- Catatan rollback

## 9. Financial Safety

Untuk fitur eksekusi trading:

- Jangan gunakan optimistic status untuk order fill finansial kritikal.
- Pastikan status eksekusi berasal dari konfirmasi backend/broker.
- Fitur darurat (kill switch) harus tetap bisa memblokir aksi eksekusi baru.
- Autonomy level harus default ke Level 1 (SIGNAL_ONLY) saat pertama kali deploy.
- Ghost Machine harus bisa di-stop dari frontend kapan saja.

## 10. Codebase Health Checks

Sebelum merge besar, jalankan health check:

```bash
# Dead module scan
python scripts/check_dead_files.py

# Full regression
python -m pytest tests/ -q

# Frontend build
cd frontend && npm run build
```

## 11. Market Scope

Proyek ini berfokus pada **Forex (24/5) dan Crypto (24/7)**. Kontribusi harus:

- Menggunakan simbol Forex (EURUSD, GBPUSD, dll) atau Crypto (BTC/USDT, ETH/USDT, dll)
- Menggunakan timestamp **UTC** secara konsisten
- Tidak menambahkan logik IDX/bursa lokal kecuali ada toggle market adapter yang valid
- Referensi `.JK` atau IDX-specific di production code akan ditolak