# Kill Switch Drill Runbook

Tujuan dokumen ini adalah memberi prosedur standar untuk menguji panic flow kill switch secara berkala tanpa menyentuh akun live.

## Scope

- Endpoint yang diuji:
  - `GET /api/system/kill-switch`
  - `POST /api/system/kill-switch/activate`
  - `POST /api/system/kill-switch/deactivate`
- Fokus verifikasi:
  - status kill switch aktif/nonaktif
  - runtimeActions dari aktivasi (scheduler stop dan cancel pending order runtime)
  - rollback ke state nonaktif setelah drill selesai

## Prasyarat

- API server berjalan dan bisa diakses dari host operator.
- Lingkungan drill harus paper/sandbox (bukan akun live trading).
- Tidak ada insiden aktif yang sedang menggunakan kill switch.

## Script Drill

Script otomatis tersedia di:

- `scripts/kill_switch_drill.ps1`

Contoh eksekusi dari root repository:

```powershell
./scripts/kill_switch_drill.ps1 -BaseUrl http://127.0.0.1:8000 -Actor ops-weekly-drill
```

Jika endpoint kill switch dilindungi auth admin + 2FA challenge:

```powershell
./scripts/kill_switch_drill.ps1 -BaseUrl http://127.0.0.1:8000 -Actor ops-weekly-drill -AuthToken "<session_token_cookie_value>" -ChallengeCode "123456"
```

Jika kill switch memang sedang aktif karena maintenance terjadwal, gunakan flag berikut:

```powershell
./scripts/kill_switch_drill.ps1 -AllowIfAlreadyActive
```

## Checklist Operasional

1. Jalankan script drill.
2. Pastikan output `status` bernilai `ok`.
3. Validasi `runtimeActions` pada output:
   - `schedulerStopped` diharapkan `true` atau scheduler memang tidak aktif.
   - `pendingOrdersCancelled` tidak negatif.
4. Pastikan `finalState.killSwitchActive` bernilai `false`.
5. Simpan output JSON ke artefak audit operasional mingguan.

## Rollback Procedure

Jika drill gagal dan kill switch tetap aktif:

1. Eksekusi endpoint rollback:

```powershell
Invoke-RestMethod -Method POST -Uri "http://127.0.0.1:8000/api/system/kill-switch/deactivate" -Body (@{ reason = "manual rollback after failed drill"; actor = "ops" } | ConvertTo-Json) -ContentType "application/json"
```

2. Verifikasi state akhir:

```powershell
Invoke-RestMethod -Method GET -Uri "http://127.0.0.1:8000/api/system/kill-switch"
```

3. Jika masih aktif, eskalasi ke on-call backend dan nonaktifkan trigger trading secara manual hingga root cause ditemukan.

## Jadwal Rehearsal

- Frekuensi rekomendasi: 1x per minggu.
- Waktu eksekusi: di luar jam market aktif.
- Owner: tim operasi / reliability.

Untuk host Windows, task mingguan bisa diregistrasi otomatis:

```powershell
./scripts/register_kill_switch_drill_task.ps1 -TaskName AutoSaham-KillSwitchWeeklyDrill -DayOfWeek Sunday -At 07:00 -BaseUrl http://127.0.0.1:8000 -Actor ops-weekly-drill
```

Jika endpoint memerlukan session admin, set environment variable token terlebih dahulu di host scheduler:

```powershell
[Environment]::SetEnvironmentVariable("AUTOSAHAM_KILL_SWITCH_DRILL_AUTH_TOKEN", "<session_token_cookie_value>", "Machine")
```

## Catatan Keamanan

- Jangan menjalankan drill terhadap endpoint production live tanpa maintenance window.
- Batasi distribusi `AuthToken` dan `ChallengeCode` hanya ke operator on-call yang berwenang.
- Audit akses endpoint kill switch secara berkala (RBAC lintas fitur masih backlog prioritas).
