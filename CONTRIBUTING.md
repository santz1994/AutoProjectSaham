# Contributing to AutoSaham

Dokumen ini menjelaskan standar kontribusi untuk menjaga keamanan, kualitas, dan kestabilan platform.

## 1. Branching

- Gunakan branch feature/fix terpisah dari master.
- Nama branch disarankan:
  - feat/<short-topic>
  - fix/<short-topic>
  - chore/<short-topic>

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

## 3. Security Rules (Wajib)

- Jangan commit secret: API key, token, private key, kredensial broker.
- Gunakan env var untuk konfigurasi sensitif.
- Gunakan mekanisme state store terenkripsi untuk data sensitif runtime.
- Untuk endpoint trading sensitif, prioritaskan server-side validation.

## 4. Local Validation

Jalankan validasi minimum sebelum PR:

Backend:
- python -m pytest tests/ -q

Frontend:
- cd frontend
- npm run type-check
- npm run build

Jika perubahan menyentuh area tertentu, jalankan test targeted terkait area tersebut.

## 5. CI and Quality Expectations

- CI harus hijau pada workflow utama.
- Hindari menurunkan kualitas lint/type-check tanpa alasan yang jelas.
- Untuk perubahan keamanan, sertakan catatan threat/risk singkat pada PR.

## 6. Docs Update Policy

Perubahan arsitektur atau flow penting harus diikuti update dokumen:

- README.md untuk setup dan usage tingkat tinggi.
- docs/ untuk panduan teknis mendalam.
- CONTRIBUTING.md jika aturan kontribusi berubah.

## 7. Review Guidelines

Dalam PR, sertakan:

- Ringkasan perubahan
- Dampak dan risiko
- Cara verifikasi
- Catatan rollback

## 8. Financial Safety

Untuk fitur eksekusi trading:

- Jangan gunakan optimistic status untuk order fill finansial kritikal.
- Pastikan status eksekusi berasal dari konfirmasi backend/broker.
- Fitur darurat (kill switch) harus tetap bisa memblokir aksi eksekusi baru.
