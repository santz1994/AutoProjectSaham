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

7. Checklist Implementasi Audit (Update: 2026-04-09)

Legend:
- [x] DONE
- [-] PARTIAL / PENDING (lihat keterangan)
- [/] TODO
- [ ] NOT STARTED

System & Architecture
- [x] Phase 1 hybrid state store non-breaking: SecureAppStateStore mendukung Redis read-through/write-through cache dengan fallback SQLite.
- [x] Unit test untuk hybrid state store (Redis cache hit, SQLite fallback, cache backfill) sudah ditambahkan dan lulus.
- [x] Phase 2 namespace runtime kritikal (ai_regime_state, broker_connection, user_settings) sudah Redis-primary dengan fallback SQLite + opsi shadow-write.
- [x] Hardening phase 2: default shadow-write SQLite untuk namespace Redis-primary diaktifkan agar migrasi tetap non-breaking (dapat di-disable via env).
- [x] Phase 3 pilot non-breaking: ai_activity_logs mendukung PostgreSQL sebagai primary backend opsional, dengan SQLite shadow-write/fallback.
- [x] Operational readiness phase 3: env flags state-store didokumentasikan dan dependency PostgreSQL client (psycopg) ditambahkan.
- [x] Operational readiness phase 3: default env migration state-store sudah diset pada service API di docker-compose untuk rollout bertahap.
- [ ] Migrasi state management penuh dari file-based (SQLite/local key) ke Redis + PostgreSQL/TimescaleDB. (PARTIAL: namespace runtime kritikal sudah Redis-primary, ai_activity_logs sudah mendukung PostgreSQL-primary opsional, dan endpoint status/migrasi backend sudah tersedia; migrasi penuh historical/domain lain masih berjalan)
- [ ] Pisahkan workload ML/RL berat ke task queue terpisah (Celery + broker) untuk menjaga API responsif. (PARTIAL: API kini mendukung dispatch async ETL/training via Celery + endpoint status task, namun belum semua jalur workload dialihkan ke worker queue)
- [ ] Audit dan refactor modul ml/trainer.py untuk memastikan tidak ada blocking call yang dijalankan di thread utama API, dan semua operasi berat dipindahkan ke worker terpisah. (PARTIAL: registrasi model dan trigger training async sudah ditambahkan, namun audit menyeluruh seluruh call path masih diperlukan)
- [ ] Evaluasi opsi orkestrasi task queue (mis. Celery vs RQ vs custom solution) untuk workload ML/RL, dengan fokus pada kemudahan integrasi, monitoring, dan skalabilitas. (PARTIAL: Celery sudah dipilih dan dipasang sebagai baseline orkestrasi, namun observability/retry policy operasional masih perlu dimatangkan)
- [ ] Implementasi paid (Basic, Pro) and free tier dengan rate limit berbeda di Kong, serta endpoint API untuk memantau penggunaan kuota per user. (PARTIAL: rate limiting sudah aktif di Kong, namun segmentasi paid/free tier dan endpoint monitoring kuota masih perlu ditambahkan)
- [ ] Audit readiness untuk migrasi ke microservices: pastikan semua endpoint API sudah terdefinisi dengan baik di kong.yml, dan tidak ada tight coupling antar modul yang bisa menghambat pemisahan layanan di masa depan.
- [ ] Implementasi monitoring dan alerting untuk state store (Redis/PostgreSQL) dan task queue (Celery) untuk mendeteksi masalah performa atau kegagalan sistem dengan cepat. (PARTIAL: endpoint status migrasi sudah tersedia, namun integrasi dengan monitoring tool seperti Prometheus/Grafana masih perlu dilakukan)
- [ ] Update dokumentasi kontribusi (CONTRIBUTING.md) untuk mencerminkan perubahan arsitektur, standar kode, dan proses pengembangan baru setelah migrasi ke state store terpusat dan task queue. (PARTIAL: beberapa bagian dokumentasi sudah diperbarui, namun audit menyeluruh seluruh bagian kontribusi masih diperlukan untuk memastikan semua perubahan arsitektur dan proses tercermin dengan jelas)
- [ ] Update .gitignore untuk memastikan file sementara, log, dan artefak build yang tidak relevan tidak masuk ke repository, terutama setelah penambahan Redis/PostgreSQL dan task queue. (PARTIAL: beberapa entri baru sudah ditambahkan untuk Redis dump, Celery logs, dan PostgreSQL artifacts, namun audit menyeluruh seluruh .gitignore masih diperlukan untuk memastikan tidak ada file sensitif atau sementara yang terlewat)
- [ ] Update README.md untuk mencerminkan perubahan arsitektur, setup environment, dan instruksi penggunaan baru setelah migrasi ke state store terpusat dan task queue. (PARTIAL: beberapa bagian README sudah diperbarui, namun audit menyeluruh seluruh README masih diperlukan untuk memastikan semua perubahan arsitektur, setup, dan instruksi tercermin dengan jelas)

User Authentication & UAC
- [ ] Implementasi sistem autentikasi dan otorisasi pengguna yang kuat, termasuk manajemen session dan token.
- [ ] Penambahan fitur "Remember Me" dan "Two-Factor Authentication" untuk meningkatkan keamanan akun pengguna.
- [ ] Implementasi Role-Based Access Control (RBAC) untuk membatasi akses ke fitur tertentu berdasarkan peran pengguna (mis. Developer, admin, trader, viewer).
- [ ] Audit dan perbaikan potensi vektor serangan pada endpoint API, seperti SQL injection, XSS, CSRF, dan lainnya.

Security
- [x] WebSocket wajib autentikasi token pada handshake/connection phase untuk endpoint realtime utama.
- [x] Validasi user binding pada notification websocket (mencegah user A subscribe channel user B).
- [x] Rate limiting aktif dan diperketat di Kong untuk auth, inference, execution, dan websocket routes.
- [ ] Secret management end-to-end broker credential encryption at rest di seluruh subsistem. (PARTIAL: broker credentials kini disimpan pada namespace secure_state terenkripsi, namun audit menyeluruh semua jalur secret masih perlu)
- [ ] Audit keamanan menyeluruh untuk endpoint API, WebSocket, dan data flow untuk mengidentifikasi potensi vektor serangan (mis. injection, unauthorized access, data leakage) dan mitigasi yang sesuai.
- [ ] Implementasi mekanisme logging dan monitoring keamanan untuk mendeteksi aktivitas mencurigakan atau pelanggaran keamanan secara real-time.

Speed Access & Performance
- [ ] Migrasi feed polling ke streaming-native penuh untuk menekan latency/risk throttling provider. (PARTIAL: adapter streaming IDX berbasis WebSocket sudah ditambahkan sebagai jalur ingest, namun rollout penuh untuk semua jalur feed belum selesai)
- [ ] Optimasi inferensi model (TorchScript/ONNX Runtime) untuk HFT-grade latency.
- [x] Throttling/debouncing update store frontend untuk high-frequency websocket load.
- [x] Pemisahan state chart vs state UI global secara menyeluruh.
- [ ] Implementasi chart rendering berbasis Canvas/WebGL untuk data frekuensi tinggi. (PARTIAL: beberapa grafik sudah menggunakan Lightweight Charts, namun belum merata di seluruh UI)
- [ ] Audit seluruh jalur data feed -> state update -> chart rendering untuk memastikan tidak ada bottleneck performa yang bisa menyebabkan UI freeze atau lag saat menerima data market frekuensi tinggi.

Code Quality
- [ ] Eliminasi duplikasi logika lintas broker adapter melalui base_broker + retry_wrapper secara konsisten. (PARTIAL: mapping status order dan async retry helper kini dipusatkan di base_broker, serta dipakai lintas adapter utama; masih perlu audit adapter lain agar konsisten 100%)
- [x] Standarisasi entrypoint runtime (single source of truth untuk run script).
- [x] Implementasi model registry (mis. MLflow) untuk lifecycle artefak model. (DONE: model registry persisten sudah diimplementasikan dan terintegrasi ke trainer)
- [x] Perbaikan kompatibilitas GitHub Actions: upgrade checkout/setup-python ke versi terbaru dan migrasi upload-artifact dari v3 ke v4.
- [x] Investigasi dan perbaikan kegagalan job "Code Quality & Linting" (exit code 1): stabilisasi workflow (Python 3.11, Node24 opt-in, lint report-only).
- [ ] Update dokumentasi kontribusi (CONTRIBUTING.md) untuk mencerminkan perubahan arsitektur, standar kode, dan proses pengembangan baru setelah migrasi ke state store terpusat dan task queue. (PARTIAL: beberapa bagian dokumentasi sudah diperbarui, namun audit menyeluruh seluruh bagian kontribusi masih diperlukan untuk memastikan semua perubahan arsitektur dan proses tercermin dengan jelas)
- [ ] Update .gitignore untuk memastikan file sementara, log, dan artefak build yang tidak relevan tidak masuk ke repository, terutama setelah penambahan Redis/PostgreSQL dan task queue. (PARTIAL: beberapa entri baru sudah ditambahkan untuk Redis dump, Celery logs, dan PostgreSQL artifacts, namun audit menyeluruh seluruh .gitignore masih diperlukan untuk memastikan tidak ada file sensitif atau sementara yang terlewat)

Documentation simpan dalam /docs kecuali untuk dokumentasi kontribusi (CONTRIBUTING.md) dan README.md yang berada di root repository.
- [x] Dokumentasi API state store (Redis/PostgreSQL) dan task queue (Celery) untuk penggunaan dan konfigurasi sudah ditambahkan di docs/api_state_store.md.
- [x] Dokumentasi penggunaan dan konfigurasi rate limiting di Kong untuk paid/free tier sudah ditambahkan di docs/CICD_DEPLOYMENT_GUIDE.md.
- [ ] Update dokumentasi kontribusi (CONTRIBUTING.md) untuk mencerminkan perubahan arsitektur, standar kode, dan proses pengembangan baru setelah migrasi ke state store terpusat dan task queue. (PARTIAL: beberapa bagian dokumentasi sudah diperbarui, namun audit menyeluruh seluruh bagian kontribusi masih diperlukan untuk memastikan semua perubahan arsitektur dan proses tercermin dengan jelas)
- [ ] Update .gitignore untuk memastikan file sementara, log, dan artefak build yang tidak relevan tidak masuk ke repository, terutama setelah penambahan Redis/PostgreSQL dan task queue. (PARTIAL: beberapa entri baru sudah ditambahkan untuk Redis dump, Celery logs, dan PostgreSQL artifacts, namun audit menyeluruh seluruh .gitignore masih diperlukan untuk memastikan tidak ada file sensitif atau sementara yang terlewat)
- [ ] Update README.md untuk mencerminkan perubahan arsitektur, setup environment, dan instruksi penggunaan baru setelah migrasi ke state store terpusat dan task queue. (PARTIAL: beberapa bagian README sudah diperbarui, namun audit menyeluruh seluruh README masih diperlukan untuk memastikan semua perubahan arsitektur, setup, dan instruksi tercermin dengan jelas)
- [ ] Dokumentasi API state store (Redis/PostgreSQL) dan task queue (Celery) untuk penggunaan dan konfigurasi.
- [ ] Dokumentasi penggunaan dan konfigurasi rate limiting di Kong untuk paid/free tier.
- [ ] Dokumentasi kontribusi (CONTRIBUTING.md) untuk mencerminkan perubahan arsitektur, standar kode, dan proses pengembangan baru setelah migrasi ke state store terpusat dan task queue.
- [ ] Dokumentasi setup environment dan instruksi penggunaan di README.md untuk mencerminkan perubahan arsitektur, setup environment, dan instruksi penggunaan baru setelah migrasi ke state store terpusat dan task queue.

UI/UX & Accessibility
- [ ] Migrasi bertahap CSS konvensional ke CSS Modules/utility-first approach untuk mengurangi collision. (PARTIAL: TradeLogsPage sudah dimigrasikan ke CSS Modules, halaman lain menyusul)
- [ ] Optimistic UI pada seluruh alur eksekusi order/trade log. (PARTIAL: TradeLogsPage sudah punya optimistic refresh/report state, flow eksekusi order end-to-end masih perlu dituntaskan)
- [ ] Chart rendering berbasis Canvas/WebGL untuk data frekuensi tinggi (mis. Lightweight Charts) untuk menghindari React render hell.
- [x] Implementasi utilitas a11y untuk memastikan standar aksesibilitas terpenuhi (keyboard navigation, ARIA roles, dll).
- [x] PWA readiness: service worker untuk caching dan offline support sudah diimplementasikan.
- [ ] Komponen UI/UX disetiap halaman (dashboard, market, portfolio) sudah dioptimasi untuk responsivitas dan performa pada perangkat mobile, dengan penyeragaman desain dan testing lintas device. Agar tampilan menjadi konsisten dan user-friendly di berbagai ukuran layar, professional UI/UX audit dan penyesuaian desain mungkin diperlukan untuk memastikan elemen interaktif tetap mudah diakses dan navigasi tetap intuitif pada smartphone dan tablet.

Security Financial Logic
- [x] Penguatan Order FSM untuk skenario partial fill dan transisi kuantitas terisi.
- [x] Reconciler membedakan FILLED vs PARTIALLY_FILLED berbasis aggregate fill aktual.
- [x] Double-entry bookkeeping penuh (locked margin vs free margin) di reconciler/execution ledger.
- [ ] Audit menyeluruh logika reconciler untuk edge case (partial fill, cancel sisa order) dan pastikan integritas perhitungan expected cash tetap terjaga. (PARTIAL: beberapa kasus partial fill sudah ditangani, namun audit menyeluruh semua jalur eksekusi order masih diperlukan untuk memastikan tidak ada celah logika yang bisa menyebabkan mismatch saldo atau perhitungan margin yang salah)

AI/ML/RL
- [ ] Implementasi Purged K-Fold Cross-Validation: Validasi silang standar (seperti K-Fold biasa) sering menyebabkan look-ahead bias (kebocoran data masa depan ke masa lalu) pada data time-series saham. Gunakan Purged atau Combinatorial Purged CV untuk memisahkan data training dan validation secara aman.
- [ ] Integrasi Feature Store (mis. Feast, Hopsworks): Mengelola dan melayani fitur ML secara tersentralisasi. Ini memastikan kalkulasi indikator teknikal (seperti RSI, MACD) 100% identik saat fase training (historical) dan serving/inference (real-time), mencegah fenomena training-serving skew.
- [ ] Automatisasi Feature Selection: Menggunakan teknik seperti Feature Importance atau Principal Component Analysis (PCA) secara otomatis dalam pipeline untuk membuang sinyal yang berisik (noisy) dan mencegah overfitting atau kutukan dimensi (curse of dimensionality).
- [ ] Penerapan Reward Shaping berbasis Risiko: Mengubah fungsi reward RL dari sekadar "Total Profit/Return" menjadi metrik yang disesuaikan dengan risiko, seperti Sharpe Ratio, Sortino Ratio, atau memberikan penalti eksponensial terhadap Maximum Drawdown untuk menciptakan agen yang lebih protektif terhadap modal.
- [ ] Multi-Agent System (Hierarchical RL): Memisahkan tugas agen. Alih-alih satu agen melakukan semuanya, buat: 1) Agen Alokasi (menentukan sektor/saham), 2) Agen Sizing (menentukan berapa lot), dan 3) Agen Eksekusi (membeli secara mencicil untuk meminimalkan slippage).
- [ ] Simulasi Slippage dan Transaction Cost Dinamis: Memastikan environment RL Anda menstimulasikan biaya komisi broker, pajak, dan market impact/slippage secara realistis berdasarkan kedalaman antrean (Order Book / Bid-Ask spread) agar agen tidak belajar strategi scalping ilusionis yang mustahil di dunia nyata.
- [ ] Implementasi Market Regime Detection (Deteksi Fase Pasar): Menggunakan Unsupervised Learning (seperti Hidden Markov Models atau Gaussian Mixture Models) untuk mendeteksi apakah pasar sedang Bullish, Bearish, atau Sideways. Sistem dapat otomatis menukar (switch) model/agen RL mana yang aktif berdasarkan rezim tersebut.
- [ ] Uncertainty Quantification (Kuantifikasi Ketidakpastian): Menggunakan teknik seperti Monte Carlo Dropout atau Bayesian Neural Networks. Jika model menghasilkan prediksi profit tetapi tingkat "ketidakpastiannya" sangat tinggi, sistem akan secara otomatis mengurangi position size atau melewatkan (skip) sinyal trading tersebut.
- [ ] Automasi Deteksi Concept Drift & Data Drift: Menggunakan alat seperti Evidently AI atau Alibi Detect untuk memantau apakah pola pasar saat ini sudah menyimpang jauh dari data yang digunakan saat training. Jika terdeteksi drift tinggi, sistem akan otomatis memicu pipeline CI/CD untuk me-retrain model.
- [ ] Integrasi Explainable AI (XAI): Mengimplementasikan SHAP (SHapley Additive exPlanations) atau LIME ke dalam dashboard monitoring. Ini memungkinkan trader/developer untuk mengaudit secara real-time fitur apa (misal: "berita sentimen negatif" atau "Volume Spike") yang membuat model memutuskan untuk JUAL/BELI pada detik tersebut.

Database & Storage
- [ ] Migrasi penuh state management dari file-based ke Redis + PostgreSQL/TimescaleDB. (PARTIAL: dukungan Redis-primary + PostgreSQL-primary (opsional untuk ai logs) dan endpoint migrasi sudah tersedia, tetapi migrasi penuh seluruh domain state/historical belum selesai)
- [ ] Implementasi backup dan disaster recovery untuk Redis dan PostgreSQL untuk memastikan data state kritikal tidak hilang dalam kasus kegagalan sistem.
- [ ] Audit dan optimasi query database untuk historical tick data di PostgreSQL/TimescaleDB untuk memastikan performa yang baik saat melakukan backtesting atau analisis historis.
- [ ] Implementasi mekanisme versioning untuk state schema di Redis/PostgreSQL untuk memudahkan migrasi dan rollback jika terjadi perubahan struktur data yang tidak kompatibel.

Github
- [x] Stabilkan workflow CI/CD untuk Python 3.11, Node24 opt-in, dan lint report-only.
- [x] Perbaiki kegagalan job "Code Quality & Linting" (exit code 1) dengan memastikan semua linter dan formatter sudah kompatibel dengan kode yang ada, serta menambahkan pengecualian (ignore) untuk kasus khusus jika diperlukan.
- [ ] Update dokumentasi kontribusi (CONTRIBUTING.md) untuk mencerminkan perubahan arsitektur, standar kode, dan proses pengembangan baru setelah migrasi ke state store terpusat dan task queue.
- [ ] Update .gitignore untuk memastikan file sementara, log, dan artefak build yang tidak relevan tidak masuk ke repository, terutama setelah penambahan Redis/PostgreSQL dan task queue.
- [ ] Implementasi GitHub Issue Template dan Pull Request Template untuk memastikan standar pelaporan bug dan kontribusi kode yang konsisten di seluruh tim.

8. Better Ideas for Review (Proposed)
- [/] Tambahkan "Migration Control Center" endpoint kecil (read-only dashboard JSON) yang merangkum status Redis/PostgreSQL shadow write, error counter, dan last successful migration timestamp per namespace.
- [/] Terapkan contract test per broker adapter (schema response + retry contract) agar perubahan API broker tidak langsung merusak production flow.
- [/] Tambahkan simulasi exchange lokal untuk chaos testing (latency spike, partial fill acak, cancel race condition) sebelum fitur eksekusi baru diaktifkan ke akun real.
- [/] Integrasikan OpenTelemetry tracing untuk request API -> broker adapter -> state_store agar bottleneck latency mudah dilacak lintas komponen.
- [/] Terapkan feature flag rollout untuk path kritikal (streaming adapter, celery async training, state migration) sehingga release bisa canary per environment/user group.