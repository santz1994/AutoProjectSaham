1. System & Architecture Aspect (Arsitektur Sistem)
  Status Saat Ini: Sistem menggunakan arsitektur Modular Monolith berbasis Python (FastAPI) dengan API Gateway (Kong), serta integrasi Machine Learning (PyTorch/Scikit-learn) dan Reinforcement Learning (Ray RLlib/Custom).
  - Kekuatan: Pemisahan pipeline yang sangat jelas (pipeline -> ml -> rl -> execution). Penggunaan kong.yml menunjukkan kesiapan menuju Microservices.
  - Celah Kritikal (Stateful Bottleneck): Penyimpanan state masih bergantung pada file-based system (data/etl.db, data/yahoo_cache.db, data/.app_state.key).
    - Dampak: Sistem ini tidak bisa di-scale secara horizontal (menjalankan banyak instance bersamaan) karena masing-masing instance akan berebut mengunci file SQLite/Key lokal.
    - Solusi: Migrasikan state management (Order FSM, Balance, Cache) dari local file ke Redis (In-Memory Datastore) dan PostgreSQL/TimescaleDB untuk data historis tick.
  - Asinkronisasi vs Komputasi Berat: FastAPI sangat bagus untuk operasi I/O (menunggu API Broker). Namun, modul ml/trainer.py dan RL memblokir Event Loop (Python GIL) jika dijalankan di thread yang sama dengan server API.
    - Solusi: Gunakan Task Queue terpisah seperti Celery + RabbitMQ/Redis khusus untuk training dan inference ML, sehingga API tetap responsif.

2. Security Aspect (Keamanan)
  - Authentication & WebSockets: Menggunakan JWT (api/auth.py). Namun, seringkali WebSocket (hooks/useWebSocket.ts) lupa divalidasi.
    - Audit: Pastikan koneksi WebSocket memerlukan token pada fase handshake awal (via URI query parameter atau auth message pertama), untuk mencegah unauthorized market data sniffing.
  - Secret Management: Terdapat src/utils/secrets.py dan .env.
    - Audit: Pastikan kunci API Broker (Stockbit, Indopremier, Ajaib) dienkripsi saat rest (At-Rest Encryption) menggunakan modul seperti cryptography.fernet. Jangan menyimpan API Key klien dalam bentuk plaintext di database/file konfigurasi.
  - Rate Limiting: Dengan adanya kong.yml, pastikan Rate Limiting plugin diaktifkan untuk mencegah serangan DDoS pada endpoint algoritma eksekusi.

3. Speed Access & Performance (Performa)
  A. Backend (Trading Engine & Data Feed)
  - Latensi Data: Jika idx_realtime_fetcher.py melakukan polling terlalu cepat tanpa menggunakan streaming API (FIX Protocol/WebSocket asli dari bursa jika ada), IP Anda berisiko diblokir oleh penyedia data, atau mengalami latensi I/O.
  - Solusi Vectorization: Pastikan komponen ML inferensi menggunakan ONNX Runtime atau mengekspor model PyTorch ke format TorchScript (JIT) untuk memangkas waktu inferensi dari milidetik ke mikrodetik. Model .joblib (Scikit-learn) cukup lambat untuk tick-by-tick trading.

  B. Frontend (React & WebSocket)
  - React Render Hell: File useTradingStore.ts (Zustand) dan ChartComponent.jsx. Jika data market masuk setiap 100ms via WebSocket, dan status portofolio di-update secara global, seluruh DOM React akan me-render ulang 10 kali per detik. Ini akan membuat CPU klien kepanasan dan browser freeze.
  - Solusi UI Speed: 
    1. Gunakan teknik Throttling/Debouncing pada store update (misal: agregasi tick menjadi rentang 500ms). 
    2. Pisahkan state untuk grafik (chart) dari state UI. Gunakan library berbasis Canvas/WebGL seperti Lightweight Charts (TradingView), jangan merender grafik SVG/DOM-based untuk data frekuensi tinggi.

4. Code Quality: Functions, Duplicated & Deprecated
  - Duplikasi Adapter Broker: Terdapat banyak file broker (indopremier.py, stockbit.py, ajaib.py, alpaca_adapter.py).
    - Audit: Terdapat potensi duplikasi logika retry atau format order. Pastikan semuanya murni memanggil kelas induk di base_broker.py dan logika error handling sepenuhnya diserahkan pada retry_wrapper.py.
  - Deprecated / Code Smells: * Penggunaan skrip PowerShell dan .bat ganda (RUN_FULLSTACK.ps1, RUN_FULLSTACK.bat, START_APP.ps1). Ini menyulitkan maintenance. Solusi: Standarkan menggunakan Makefile atau docker-compose up sebagai satu-satunya entry point.
    - Terdapat banyak file model historis (model_17755...joblib). Sistem perlu mekanisme MLflow atau Model Registry untuk menghindari penumpukan file binary model statis (bloatware) di dalam repository.

5. UI/UX & Accessibility Aspect (Antarmuka)
  - Kelebihan: Implementasi utils/a11y.js, responsivitas, dan PWA (service-worker.js) menunjukkan standar desain modern yang sangat baik (Aksesibel dan Mobile-Ready).
  - Manajemen CSS: Penggunaan CSS konvensional (styles/dashboard.css, styles/market.css, dll) dalam jumlah masif dapat menyebabkan CSS Collision (konflik nama class) seiring berkembangnya aplikasi.
    - Rekomendasi: Secara perlahan migrasikan ke CSS Modules (.module.css), atau Utility-first framework seperti Tailwind CSS, atau CSS-in-JS agar desain lebih tersentralisasi dan ukuran bundle (CSS) lebih kecil.
  - UX pada Eksekusi: Pastikan ada mekanisme Optimistic UI Updates untuk TradeLogsPage.jsx dan Order form. Ketika user menekan "BUY", UI harus langsung merespons "Processing...", bukan freeze menunggu konfirmasi dari backend.

6. Security Financial Logic (Logika Transaksi)
  Reconciler (src/execution/reconciler.py): Modul ini bertugas mencocokkan saldo internal dengan saldo di Broker.
  - Celah: Bagaimana jika terjadi Partial Fill (order hanya tereksekusi sebagian)? Apakah State Machine (order_fsm.py) dapat menangani pembatalan (cancel) pada remaining quantity tanpa merusak perhitungan Expected Cash?
  - Audit Solusi: Pastikan reconciler.py menerapkan logika Double-Entry Bookkeeping secara memori, di mana dana yang dialokasikan untuk order (locked margin) dipisah secara ketat dari dana bebas (free margin).

7. Checklist Implementasi Audit (Update: 2026-04-07)

Legend:
- [x] DONE
- [ ] PARTIAL / PENDING (lihat keterangan)

System & Architecture
- [ ] Migrasi state management dari file-based (SQLite/local key) ke Redis + PostgreSQL/TimescaleDB. (PARTIAL: infrastruktur Redis/PostgreSQL sudah ada di docker-compose, tetapi state utama aplikasi masih file-based/SQLite)
- [ ] Pisahkan workload ML/RL berat ke task queue terpisah (Celery + broker) untuk menjaga API responsif. (PARTIAL: beberapa workload sudah dijalankan di executor/background, belum full queue orchestration)

Security
- [x] WebSocket wajib autentikasi token pada handshake/connection phase untuk endpoint realtime utama.
- [x] Validasi user binding pada notification websocket (mencegah user A subscribe channel user B).
- [x] Rate limiting aktif dan diperketat di Kong untuk auth, inference, execution, dan websocket routes.
- [ ] Secret management end-to-end broker credential encryption at rest di seluruh subsistem. (PARTIAL: secure state store terenkripsi sudah ada, namun audit menyeluruh semua jalur secret masih perlu)

Speed Access & Performance
- [ ] Migrasi feed polling ke streaming-native penuh untuk menekan latency/risk throttling provider.
- [ ] Optimasi inferensi model (TorchScript/ONNX Runtime) untuk HFT-grade latency.
- [ ] Throttling/debouncing update store frontend untuk high-frequency websocket load.
- [ ] Pemisahan state chart vs state UI global secara menyeluruh.

Code Quality
- [ ] Eliminasi duplikasi logika lintas broker adapter melalui base_broker + retry_wrapper secara konsisten.
- [ ] Standarisasi entrypoint runtime (single source of truth untuk run script).
- [ ] Implementasi model registry (mis. MLflow) untuk lifecycle artefak model.

UI/UX & Accessibility
- [ ] Migrasi bertahap CSS konvensional ke CSS Modules/utility-first approach untuk mengurangi collision.
- [ ] Optimistic UI pada seluruh alur eksekusi order/trade log.

Security Financial Logic
- [x] Penguatan Order FSM untuk skenario partial fill dan transisi kuantitas terisi.
- [x] Reconciler membedakan FILLED vs PARTIALLY_FILLED berbasis aggregate fill aktual.
- [ ] Double-entry bookkeeping penuh (locked margin vs free margin) di reconciler/execution ledger.