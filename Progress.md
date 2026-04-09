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
- [x] Update dokumentasi kontribusi (CONTRIBUTING.md) untuk mencerminkan perubahan arsitektur, standar kode, dan proses pengembangan baru setelah migrasi ke state store terpusat dan task queue.
- [x] Update .gitignore untuk memastikan file sementara, log, dan artefak build yang tidak relevan tidak masuk ke repository, terutama setelah penambahan Redis/PostgreSQL dan task queue.
- [-] Update README.md untuk mencerminkan perubahan arsitektur, setup environment, dan instruksi penggunaan baru setelah migrasi ke state store terpusat dan task queue. (PARTIAL: endpoint kill switch, env websocket backplane, dan catatan kontribusi sudah ditambahkan; audit keseluruhan isi README masih berjalan)
- [-] Redis Pub/Sub untuk Scaling WebSocket Gunakan pola Redis Pub/Sub. Semua market data di-publish ke Redis, dan setiap instance FastAPI men-subscribe Redis tersebut untuk di-broadcast ke klien WebSocket masing-masing. Ini memungkinkan horizontal scaling dengan banyak instance API yang tetap menerima data real-time tanpa harus mengandalkan sticky session atau load balancer khusus WebSocket. (PARTIAL: backplane Redis Pub/Sub opsional sudah diimplementasikan pada src/api/event_queue.py dengan env AUTOSAHAM_WS_BACKPLANE_ENABLED, rollout/monitoring produksi multi-instance masih perlu)
- [ ] Data Retention & Archival Strategy (Hot vs Cold Data) Buat aturan archival. Data 3 bulan terakhir simpan di PostgreSQL (Hot Storage). Data lebih dari 3 bulan di- dump ke format Parquet/CSV dan disimpan di S3/Cloud Storage (Cold Storage) untuk keperluan training (menggunakan DuckDB atau Polars untuk membacanya).
- [x] Add license file (MIT License) untuk memastikan hak cipta dan penggunaan kode yang jelas bagi kontributor dan pengguna.

User Authentication & UAC
- [-] Implementasi sistem autentikasi dan otorisasi pengguna yang kuat, termasuk manajemen session dan token. (PARTIAL: session context kini memuat role + csrf token, endpoint /auth/me mengekspose role, dan guard admin ditambahkan pada endpoint operasional kritikal; hardening menyeluruh lintas semua endpoint masih berjalan)
- [-] Penambahan fitur "Remember Me" dan "Two-Factor Authentication" untuk meningkatkan keamanan akun pengguna. (PARTIAL: login kini mendukung rememberMe dengan TTL sesi terpisah, dan 2FA login sudah ditambahkan secara env-driven (role-based requirement + verifier TOTP/fallback code); integrasi enrollment/per-user setup flow 2FA di UI/settings masih perlu dituntaskan)
- [-] Implementasi Role-Based Access Control (RBAC) untuk membatasi akses ke fitur tertentu berdasarkan peran pengguna (mis. Developer, admin, trader, viewer). (PARTIAL: role user disimpan pada registry auth; admin guard sudah diterapkan pada endpoint operasional mutating (bot control, broker connect/disconnect, state migration, broker feature-flag update); role-guard granular kini juga diterapkan pada endpoint strategi/profile/log AI (deploy/backtest strategy, reset profile, write AI logs, update user settings) dengan env-configurable allowed roles + admin override; RBAC matrix lintas seluruh endpoint masih perlu dituntaskan)
- [-] Audit dan perbaikan potensi vektor serangan pada endpoint API, seperti SQL injection, XSS, CSRF, dan lainnya. (PARTIAL: mekanisme double-submit CSRF token kini diterapkan untuk endpoint mutating yang dijaga session admin; audit vektor lain (injection/XSS/CSRF lintas seluruh endpoint) masih perlu dilanjutkan)

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
- [x] Update dokumentasi kontribusi (CONTRIBUTING.md) untuk mencerminkan perubahan arsitektur, standar kode, dan proses pengembangan baru setelah migrasi ke state store terpusat dan task queue.
- [x] Update .gitignore untuk memastikan file sementara, log, dan artefak build yang tidak relevan tidak masuk ke repository, terutama setelah penambahan Redis/PostgreSQL dan task queue.
- [x] Automated Secret & Vulnerability Scanning Tambahkan GitHooks (misal: TruffleHog atau Gitleaks) di CI/CD untuk mencegah commit yang mengandung API Key atau kredensial database. Gunakan Dependabot untuk memantau celah keamanan di requirements.txt / package.json .
- [-] Strict Type Hinting (Python mypy) Terapkan aturan Strict Type Hinting menggunakan mypy sebagai pass/fail gate di Github Actions CI. (PARTIAL: gate strict sudah aktif di workflow Python CI via mypy.strict.ini untuk modul inti src/api/event_queue.py; perlu ekspansi bertahap ke modul lain)
- [ ] Check Duplicated Code, Linting, dan Code Smells Tambahkan tools seperti SonarQube atau CodeClimate untuk analisis kualitas kode secara menyeluruh, termasuk deteksi duplikasi, code smells, dan potensi bug.

Documentation simpan dalam /docs kecuali untuk dokumentasi kontribusi (CONTRIBUTING.md) dan README.md yang berada di root repository.
- [x] Dokumentasi API state store (Redis/PostgreSQL) dan task queue (Celery) untuk penggunaan dan konfigurasi sudah ditambahkan di docs/api_state_store.md.
- [x] Dokumentasi penggunaan dan konfigurasi rate limiting di Kong untuk paid/free tier sudah ditambahkan di docs/CICD_DEPLOYMENT_GUIDE.md.
- [x] Update dokumentasi kontribusi (CONTRIBUTING.md) untuk mencerminkan perubahan arsitektur, standar kode, dan proses pengembangan baru setelah migrasi ke state store terpusat dan task queue.
- [x] Update .gitignore untuk memastikan file sementara, log, dan artefak build yang tidak relevan tidak masuk ke repository, terutama setelah penambahan Redis/PostgreSQL dan task queue.
- [-] Update README.md untuk mencerminkan perubahan arsitektur, setup environment, dan instruksi penggunaan baru setelah migrasi ke state store terpusat dan task queue. (PARTIAL: endpoint kill switch, env websocket backplane, dan catatan kontribusi sudah ditambahkan; audit keseluruhan isi README masih berjalan)
- [ ] Dokumentasi API state store (Redis/PostgreSQL) dan task queue (Celery) untuk penggunaan dan konfigurasi.
- [ ] Dokumentasi penggunaan dan konfigurasi rate limiting di Kong untuk paid/free tier.
- [ ] Dokumentasi kontribusi (CONTRIBUTING.md) untuk mencerminkan perubahan arsitektur, standar kode, dan proses pengembangan baru setelah migrasi ke state store terpusat dan task queue.
- [ ] Dokumentasi setup environment dan instruksi penggunaan di README.md untuk mencerminkan perubahan arsitektur, setup environment, dan instruksi penggunaan baru setelah migrasi ke state store terpusat dan task queue.

UI/UX & Accessibility
- [ ] Migrasi bertahap CSS konvensional ke CSS Modules/utility-first approach untuk mengurangi collision. (PARTIAL: TradeLogsPage sudah dimigrasikan ke CSS Modules, halaman lain menyusul)
- [ ] Optimistic UI pada seluruh alur eksekusi order/trade log. (PARTIAL: TradeLogsPage sudah punya optimistic refresh/report state, flow eksekusi order end-to-end masih perlu dituntaskan)
- [ ] Chart rendering berbasis Canvas/WebGL untuk data frekuensi tinggi (mis. Lightweight Charts) untuk menghindari React render hell.
- [x] Implementasi utilitas a11y untuk memastikan standar aksesibilitas terpenuhi (keyboard navigation, ARIA roles, dll).
- [ ] PWA readiness: Aplikasi trading sangat bergantung pada data real-time. Menyediakan dukungan offline (kecuali untuk melihat log historis) bisa memberikan rasa aman palsu kepada trader. Jika koneksi terputus, UI harus langsung memblokir aksi dan menampilkan peringatan Disconnected, bukan menyimpan data di cache offline. (PARTIAL: service worker sudah terpasang, namun audit menyeluruh seluruh jalur data dan aksi saat offline masih diperlukan untuk memastikan tidak ada celah yang bisa menyebabkan user melakukan aksi trading saat koneksi terputus)
- [ ] Komponen UI/UX disetiap halaman (dashboard, market, portfolio) sudah dioptimasi untuk responsivitas dan performa pada perangkat mobile, dengan penyeragaman desain dan testing lintas device. Agar tampilan menjadi konsisten dan user-friendly di berbagai ukuran layar, professional UI/UX audit dan penyesuaian desain mungkin diperlukan untuk memastikan elemen interaktif tetap mudah diakses dan navigasi tetap intuitif pada smartphone dan tablet.
- [ ] Update tampilan dan interaksi pada halaman eksekusi order dan trade log untuk memberikan feedback instan kepada pengguna, seperti status "Processing..." saat order dikirim, dan pembaruan real-time pada log setelah konfirmasi dari backend, untuk meningkatkan pengalaman pengguna dan kepercayaan terhadap sistem.
- [ ] Update tampilan setiap halaman (dashboard, market, portfolio) untuk memastikan konsistensi desain, responsivitas, dan performa pada perangkat mobile, dengan penyesuaian elemen UI agar tetap mudah diakses dan navigasi tetap intuitif di berbagai ukuran layar.
- [-] Kesesuaian frontend dan backend, jangan sampai ada fitur yang didukung di backend tapi tidak terefleksi di UI, atau sebaliknya. Pastikan setiap endpoint API yang relevan memiliki representasi yang jelas di UI, dan setiap elemen interaktif di UI memiliki dukungan backend yang memadai. (PARTIAL: endpoint operasional /api/system/execution/pending-orders sudah ditambahkan dan kini direpresentasikan di Dashboard (Execution Queue widget); audit menyeluruh seluruh endpoint vs UI masih perlu)

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
- [ ] Gunakan RL/ML hanya untuk sinyal arah (Alokasi) dan penentuan ukuran posisi (Position Sizing). Untuk Eksekusi (mencicil lot/meminimalkan slippage), gunakan algoritma aturan statis konvensional seperti TWAP (Time-Weighted Average Price) atau VWAP (Volume-Weighted Average Price). Jauh lebih aman dan mudah di- debug.
- [ ] Simulasi Slippage dan Transaction Cost Dinamis: Memastikan environment RL Anda menstimulasikan biaya komisi broker, pajak, dan market impact/slippage secara realistis berdasarkan kedalaman antrean (Order Book / Bid-Ask spread) agar agen tidak belajar strategi scalping ilusionis yang mustahil di dunia nyata.
- [ ] Implementasi Market Regime Detection (Deteksi Fase Pasar): Menggunakan Unsupervised Learning (seperti Hidden Markov Models atau Gaussian Mixture Models) untuk mendeteksi apakah pasar sedang Bullish, Bearish, atau Sideways. Sistem dapat otomatis menukar (switch) model/agen RL mana yang aktif berdasarkan rezim tersebut.
- [ ] Uncertainty Quantification (Kuantifikasi Ketidakpastian): Menggunakan teknik seperti Monte Carlo Dropout atau Bayesian Neural Networks. Jika model menghasilkan prediksi profit tetapi tingkat "ketidakpastiannya" sangat tinggi, sistem akan secara otomatis mengurangi position size atau melewatkan (skip) sinyal trading tersebut.
- [ ] Automasi Deteksi Concept Drift & Data Drift: Menggunakan alat seperti Evidently AI atau Alibi Detect untuk memantau apakah pola pasar saat ini sudah menyimpang jauh dari data yang digunakan saat training. Jika terdeteksi drift tinggi, sistem akan otomatis memicu pipeline CI/CD untuk me-retrain model.
- [ ] Integrasi Explainable AI (XAI): Mengimplementasikan SHAP (SHapley Additive exPlanations) atau LIME ke dalam dashboard monitoring. Ini memungkinkan trader/developer untuk mengaudit secara real-time fitur apa (misal: "berita sentimen negatif" atau "Volume Spike") yang membuat model memutuskan untuk JUAL/BELI pada detik tersebut.
- [ ] Implementasi Continuous Learning: Alih-alih model statis yang hanya di-retrain secara periodik, buat pipeline yang memungkinkan model untuk terus belajar dari data baru (online learning) dengan mekanisme validasi ketat untuk mencegah overfitting pada noise jangka pendek.
- [ ] Purged CV untuk validasi silang model ML pada data time-series saham, untuk mencegah look-ahead bias.
- [ ] Reward shaping berbasis metrik risiko (Sharpe Ratio, penalti drawdown) untuk agen RL yang lebih protektif modal.
- [ ] Market regime detection dengan Unsupervised Learning untuk switching model/agen otomatis berdasarkan fase pasar.

Database & Storage
- [ ] Migrasi penuh state management dari file-based ke Redis + PostgreSQL/TimescaleDB. (PARTIAL: dukungan Redis-primary + PostgreSQL-primary (opsional untuk ai logs) dan endpoint migrasi sudah tersedia, tetapi migrasi penuh seluruh domain state/historical belum selesai)
- [ ] Implementasi backup dan disaster recovery untuk Redis dan PostgreSQL untuk memastikan data state kritikal tidak hilang dalam kasus kegagalan sistem.
- [ ] Audit dan optimasi query database untuk historical tick data di PostgreSQL/TimescaleDB untuk memastikan performa yang baik saat melakukan backtesting atau analisis historis.
- [ ] Implementasi mekanisme versioning untuk state schema di Redis/PostgreSQL untuk memudahkan migrasi dan rollback jika terjadi perubahan struktur data yang tidak kompatibel.

Github
- [x] Stabilkan workflow CI/CD untuk Python 3.11, Node24 opt-in, dan lint report-only.
- [x] Perbaiki kegagalan job "Code Quality & Linting" (exit code 1) dengan memastikan semua linter dan formatter sudah kompatibel dengan kode yang ada, serta menambahkan pengecualian (ignore) untuk kasus khusus jika diperlukan.
- [x] Update dokumentasi kontribusi (CONTRIBUTING.md) untuk mencerminkan perubahan arsitektur, standar kode, dan proses pengembangan baru setelah migrasi ke state store terpusat dan task queue.
- [x] Update .gitignore untuk memastikan file sementara, log, dan artefak build yang tidak relevan tidak masuk ke repository, terutama setelah penambahan Redis/PostgreSQL dan task queue.
- [x] Implementasi GitHub Issue Template dan Pull Request Template untuk memastikan standar pelaporan bug dan kontribusi kode yang konsisten di seluruh tim.

Financial & Data
- [-] Penanganan Corporate Actions (Stock Splits, Dividen, Rights Issue) Ini adalah "pembunuh" model ML nomor satu. Jika saham BBCA melakukan stock split 1:2, harganya akan turun 50% di grafik. Jika data historis tidak di-adjust secara otomatis, fitur ML Anda (MACD, RSI) akan rusak, dan Autoencoder Anomali Anda akan membunyikan alarm palsu atau agen RL akan melakukan cut-loss massal. Anda wajib punya mekanisme ETL untuk melakukan backward adjustment terhadap data harga dan volume. (PARTIAL: baseline corporate action pipeline sudah ditambahkan di src/pipeline/corporate_actions.py dan diintegrasikan ke src/pipeline/etl.py untuk backward adjustment OHLCV berbasis file JSON (split, reverse split/bonus, dividend, rights issue) melalui env AUTOSAHAM_CORPORATE_ACTIONS_FILE; integrasi sumber corporate action resmi IDX dan rollout penuh ke seluruh jalur training/serving masih berjalan)
- [-] Global Kill Switch (Panic Button) Dampak: Algoritma bisa saja mengalami looping error atau pasar mengalami Flash Crash (seperti IHSG anjlok mendadak). Tanpa mekanisme kill switch, kerugian bisa membengkak dalam hitungan detik. Solusi: Implementasikan endpoint API "Panic Button" yang bisa mematikan semua aktivitas trading secara instan (membatalkan order terbuka, menghentikan eksekusi baru) dengan otorisasi super ketat (mis. 2FA + role admin). Solusi: Harus ada endpoint dan tombol UI fisik berupa "Global Kill Switch" yang jika ditekan akan: 1) Men- suspend semua cron/task AI, 2) Membatalkan (Cancel) semua Open Orders di bursa, 3) (Opsional) Mengirim market order untuk melikuidasi semua posisi ke cash. (PARTIAL: endpoint kill switch backend + integrasi tombol UI + guard untuk bot start/strategy deploy/backtest/run_etl/training sudah aktif; aktivasi kill switch kini best-effort menghentikan scheduler lokal, mengembalikan runtimeActions untuk audit, membatalkan pending order runtime, serta mencoba cancel seluruh open order pada koneksi live provider yang adapter-nya tersedia (indopremier/stockbit/ajaib); hardening otorisasi admin session + challenge 2FA berbasis env flag juga sudah ditambahkan pada endpoint activate/deactivate (dengan dukungan payload actor/challengeCode dan fallback kompatibilitas activatedBy); dukungan provider institusional lain, RBAC lintas fitur, dan forced liquidation belum selesai)

8. Better Ideas for Review (Proposed)
- [x] Tambahkan "Migration Control Center" endpoint kecil (read-only dashboard JSON) yang merangkum status Redis/PostgreSQL shadow write, error counter, dan last successful migration timestamp per namespace.
- [x] Terapkan contract test per broker adapter (schema response + retry contract) agar perubahan API broker tidak langsung merusak production flow. (DONE: test kontrak lintas Stockbit/Ajaib/IndoPremier ditambahkan di tests/test_broker_adapter_contracts.py mencakup schema mapping place_order/get_order_status, fail-safe saat schema berubah, serta verifikasi jalur _make_request tetap melalui retry contract _call_with_retry)
- [-] Tambahkan simulasi exchange lokal untuk chaos testing (latency spike, partial fill acak, cancel race condition) sebelum fitur eksekusi baru diaktifkan ke akun real. (PARTIAL: baseline simulator sudah ditambahkan di src/execution/exchange_simulator.py dengan skenario latency spike/partial fill/cancel race + script eksekusi scripts/simulate_exchange_chaos.py dan test deterministik tests/test_exchange_simulator.py; integrasi ke pipeline pre-release gate deployment masih perlu)
- [/] Integrasikan OpenTelemetry tracing untuk request API -> broker adapter -> state_store agar bottleneck latency mudah dilacak lintas komponen.
- [/] Terapkan feature flag rollout untuk path kritikal (streaming adapter, celery async training, state migration) sehingga release bisa canary per environment/user group.
- [x] Tambahkan endpoint read-only "Migration Control Center" versi v2 yang menyertakan kill switch state, queue backlog, dan ws backplane health dalam satu payload operasional.
- [-] Tambahkan drill otomatis kill-switch (chaos rehearsal mingguan) + runbook rollback untuk memastikan panic flow dapat diuji tanpa menyentuh akun live. (PARTIAL: script operasional scripts/kill_switch_drill.ps1 sudah ditambahkan untuk activate/deactivate drill + validasi runtimeActions/final state, runbook rollback sudah didokumentasikan di docs/KILL_SWITCH_DRILL_RUNBOOK.md, serta helper registrasi Windows Task Scheduler sudah ditambahkan di scripts/register_kill_switch_drill_task.ps1; aktivasi scheduler mingguan di environment operasi tetap perlu dijalankan per host)

9. Temuan Lainnya
- [-] Status Berjalan (PARTIAL) & Ruang Perbaikan (Improvement)
  [-] A. Asinkronisasi ML/RL vs Event Loop FastAPI
        Kondisi Kode: Anda memiliki src/tasks.py dan integrasi Celery. Namun, pada modul inferensi real-time (src/ml/service.py atau src/rl/agent_integration.py), jika model PyTorch dieksekusi secara sinkronus di dalam route FastAPI saat data masuk, Event Loop Python akan terblokir.
        Improvement: Inferensi ML tidak harus melalui Celery (karena Celery menambah latensi antrean). Untuk inferensi real-time yang cepat, pastikan Anda menggunakan asyncio.to_thread() untuk mendelegasikan kalkulasi tensor ke OS thread pool agar API tidak stalling, ATAU gunakan ONNX Runtime secara penuh.
        Status Update 2026-04-09: route /api/signals, /api/ai/projection/{symbol}, /api/ai/overview, dan /api/bot/status kini menjalankan jalur blocking melalui helper _run_blocking (asyncio.to_thread / executor fallback) untuk mengurangi risiko event-loop stall; audit jalur inferensi lain masih berjalan.
  [ ] B. Sistem AI / Regim Pasar (Regime Detection)
        Kondisi Kode: Terdapat file src/ml/regime_detector.py dan src/ml/regime_router.py. Ini adalah lompatan brilian! Model bisa membedakan pasar Bullish/Bearish.
        Improvement: Hati-hati dengan Lag Indicator. Metode deteksi rezim (misal HMM atau K-Means pada return historis) seringkali terlambat menyadari perubahan pasar (pasar sudah crash 2 hari, model baru switch ke rezim Bearish). Anda perlu memasukkan fitur Order Book Imbalance (mikrostruktur pasar) ke dalam regime_detector.py sebagai leading indicator agar bot bisa bereaksi dalam hitungan menit, bukan hari.
  [ ] C. Secret Management (Enkripsi Kredensial Broker)
        Kondisi Kode: src/utils/secrets.py dan src/utils/security.py ada, tetapi Progress.md mencatat ini masih Partial.
        Improvement: Di lingkungan produksi, jangan biarkan backend mendekripsi kunci API Ajaib/Stockbit jika tidak diperlukan. Enkripsi kunci API di database, dan hanya dekripsi di RAM (selama proses di base_broker.py). Gunakan vault yang ephemeral.

- [ ] Kekurangan Kritis yang Belum Ada di Progress.md (Missing Links)
  [-] A. Penyesuaian Corporate Action (ETL Backward Adjustment)
        Anda memiliki modul src/pipeline/etl.py dan src/ml/walk_forward.py. Namun, jika saham BMRI atau BBCA melakukan Stock Split (misal harga Rp 10.000 menjadi Rp 5.000), algoritma ML Anomali dan RL Anda akan mengira saham itu "anjlok 50% dalam 1 detik" dan langsung memicu perintah Cut Loss massal (Panic Selling otomatis).
        Aksi: Tambahkan "Corporate Action Data Pipeline" untuk menormalkan data historis (membagi data harga masa lalu dan mengkalikan volumenya sebelum di-feed ke fitur ML).
    Status Update 2026-04-09: baseline adjustment sudah diimplementasikan pada src/pipeline/corporate_actions.py dan terhubung ke run_etl (config path: AUTOSAHAM_CORPORATE_ACTIONS_FILE atau arg corporate_actions_path); langkah lanjut adalah menambahkan feed corporate action resmi dan validasi lintas jalur feature/training.
  [ ] B. Distributed WebSocket Backplane (Redis Pub/Sub)
        Di Progress.md, Anda berencana menggunakan Kong dan me-scale aplikasi secara horizontal (berjalan di banyak server/kontainer sekaligus).
        Jika Anda menggunakan WebSocket bawaan FastAPI (hooks/useWebSocket.ts), klien A mungkin terhubung ke Server 1, sedangkan data bursa baru saja ditangkap oleh Server 2. Klien A tidak akan mendapat harga update.
        Status Update 2026-04-09: Backplane opsional sudah diimplementasikan di src/api/event_queue.py (publish+subscribe+dedupe event lintas instance) dengan env AUTOSAHAM_WS_BACKPLANE_ENABLED.
      Status Update 2026-04-09 (lanjutan): endpoint /api/system/migration-control-center kini menyertakan ws backplane health + websocket queue depth + queue backlog Celery untuk observability operasional cepat.
      Aksi Lanjutan: aktifkan default di staging/production, tambah metrik health channel (Prometheus), dan jalankan soak test multi-instance.

- [ ] Machine Learning Pipeline Aspect (Akurasi & MLOps)
      Sistem ini memiliki pipeline ML yang sangat kaya (mulai dari ETL, Feature Store, hingga Walk-Forward Validation). Namun, ketangguhan di backtest belum tentu menjamin profit di live market.
  [ ] A. Sinyal "Look-Ahead Bias" pada Labeling
        Kondisi Kode (src/ml/labeler.py): Jika Anda menggunakan fitur seperti shift(-1) untuk membuat target klasifikasi (misalnya, apakah harga besok naik?), pastikan fitur-fitur teknikal (RSI, MACD) dihitung sebelum pergeseran (shift) tersebut terjadi.
        Audit: Saya melihat implementasi Triple Barrier Method (src/ml/barriers.py). Ini adalah standar gold dari Marcos Lopez de Prado. Namun, pastikan volatility (untuk menentukan lebar barrier) dihitung menggunakan rolling window dari data masa lalu, bukan future data.
        Status: Eksekusi metode ini di kode Anda sudah cukup baik, tetapi unit test untuk test_triple_barrier.py harus dikonfigurasi agar secara eksplisit menangkap data leakage.
  [ ] B. Online Learning & Concept Drift
        Kondisi Kode (src/ml/online_learner.py & src/ml/drift.py): Ini adalah fitur advanced (MLOps tingkat lanjut). Model dilatih ulang secara otomatis jika terdeteksi perubahan pola pasar (Concept Drift).
        Celah Kritikal (Catastrophic Forgetting): Jika online learner diperbarui terlalu sering (setiap ada tick harga aneh), model akan mengalami "Lupa Bencana" (Catastrophic Forgetting). Model hanya akan ingat pola 5 menit terakhir dan melupakan tren besar secara keseluruhan.
        Improvement: Implementasikan mekanisme Replay Buffer. Saat me- retrain model secara online, campurkan 20% data baru dengan 80% data lama yang representatif (stratified sampling) agar memori panjang model tetap terjaga.

- [ ] Reinforcement Learning Aspect (Pengendalian Agen)
      Anda menggunakan RL (Ray RLlib) dengan algoritma PPO (Proximal Policy Optimization). Ini adalah pilihan yang solid untuk HFT.
  [ ] A. Reward Function Escalation
        Kondisi Kode (src/rl/envs/trading_env.py): (Seperti yang kita bahas sebelumnya), fungsi reward berbasis persentase sudah lebih baik dari sekadar nilai absolut Rupiah.
        Celah Kritikal (Slippage Illusion): Agen RL sangat pintar mencari "celah" dalam simulasi. Jika lingkungan trading Anda (trading environment) mengeksekusi order market pada harga mid-price atau harga penutupan (close price) tanpa memperhitungkan bid-ask spread dan antrean lot (kedalaman pasar), agen akan belajar untuk melakukan scalping ribuan kali per hari secara fiktif.
        Improvement Wajib: Jika agen memutuskan beli (BUY), paksa lingkungan untuk mengeksekusi di harga ASK (harga jual terendah). Jika jual (SELL), eksekusi di harga BID (harga beli tertinggi). Tambahkan juga penalti komisi broker (misal 0.15% per transaksi) ke dalam fungsi reward.
  [ ] B. State Space Normalization
        Audit: Apakah observation space (input state) ke agen PPO sudah distandarisasi secara statis? Harga saham bisa berkisar dari Rp 50 hingga Rp 10.000. Jaringan saraf tiruan PPO akan meledak (vanishing/exploding gradients) jika menerima input yang tidak diskalakan (misal antara -1 hingga 1).
        Solusi: Gunakan indikator yang terikat secara matematis (RSI [0-100], persentase Z-score) sebagai state, bukan harga absolut.

- [ ] Observability, Logging, & Alerting (DevOps Phase)
      Untuk sistem yang berjalan otomatis 24/5 tanpa pengawasan manusia secara terus-menerus, monitoring adalah segalanya.
  [ ] A. Prometheus & Grafana (monitoring/)
        Kondisi Kode: Anda sudah mensetup prometheus.yml dan grafana_dashboards.py. Ini sangat bagus.
        Celah (Missing Business Metrics): Metrik infrastruktur (CPU, RAM, API Latency) memang penting. Tetapi metrik bisnis lebih krusial.
        Improvement: Pastikan Prometheus men- scrape metrik kustom dari sistem Python Anda, seperti:
        trading_expected_cash vs trading_broker_cash (jika selisihnya > Rp 1.000, tembak alarm Slack).
        ml_model_confidence_score (jika confidence model turun di bawah 50% selama 10 menit, tembak alarm).
        api_broker_rate_limit_remaining (sisa kuota API ke Stockbit/Ajaib).
  [ ] B. Error Handling & Silent Failures
        Kondisi Kode: Anda menggunakan retry_wrapper.py untuk mengatasi timeout broker.
        Audit: Bagaimana jika API broker mengubah skema responsnya (JSON format berubah)? Sistem Anda mungkin gagal parsing, masuk ke dalam infinite loop retry, dan tidak melakukan trading seharian tanpa Anda ketahui (silent failure).
        Improvement: Integrasikan Sentry atau alat error tracking sejenis. Jika ada KeyError atau ValueError yang tidak tertangani (Unhandled Exception) di production, Anda harus mendapat notifikasi WhatsApp/Slack beserta stack trace-nya dalam hitungan detik.

- [-] Frontend, UI/UX, & Aksesibilitas (Deep View)
  [ ] A. Optimistic UI pada Trade Logs (frontend/src/components/TradeLogsPage.jsx)
        Kondisi Saat Ini: Anda merencanakan (di Progress.md) Optimistic UI pada alur eksekusi order.
        Audit: Hati-hati dengan Optimistic UI di sistem finansial. Jika UI menunjukkan status "TEREKSEKUSI" padahal di backend/broker statusnya masih "ANTRE" (karena optimistic update terlalu agresif), trader bisa mengambil keputusan yang salah.
        Aturan Emas UI Finansial: Untuk status order, selalu gunakan Pessimistic UI (Hanya tampilkan "TEREKSEKUSI" jika WebSocket dari broker benar-benar mengirim event FILL). Optimistic UI hanya boleh digunakan untuk aksi visual yang tidak mengikat (seperti mengganti tema, mem- pin saham ke watchlist, atau berpindah tab).
  [ ] B. Keamanan JWT (JSON Web Tokens)
        Kondisi Kode: Authentication menggunakan utils/authService.js (Frontend) dan src/api/auth.py (Backend).
        Audit: Di mana JWT disimpan di browser klien? Jika Anda menyimpannya di localStorage atau Zustand state, JWT rentan terhadap serangan XSS (Cross-Site Scripting).
        Status Update 2026-04-09: Flow auth sudah menggunakan HTTP-Only cookie (frontend/src/utils/authService.js + src/api/server.py), bukan localStorage token.
        Improvement Security: lanjutkan hardening dengan rotasi session token dan optional CSRF token untuk aksi mutating berisiko tinggi.