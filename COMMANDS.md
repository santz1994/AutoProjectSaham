╔═══════════════════════════════════════════════════════════════════════════╗
║                   AutoSaham - RUN COMMANDS                                ║
║              Backend + Frontend untuk Development & Production            ║
╚═══════════════════════════════════════════════════════════════════════════╝

OPTION 1: PRODUCTION MODE (Frontend Built, Served by Backend)
═════════════════════════════════════════════════════════════════════════════

Command:
  python -m src.main --api

OR:
  python -m uvicorn src.api.server:app --host 127.0.0.1 --port 8000 --reload

Access:
  🌐 Web UI:  http://localhost:8000/ui       (Built frontend from dist/)
  📊 Health:  http://localhost:8000/health
  🔗 API:     http://localhost:8000/api/portfolio

Use Case:
  ✅ Production deployment
  ✅ Testing with built frontend
  ✅ No npm/Node.js needed (backend serves static files)


OPTION 2: DEVELOPMENT MODE (Separate Backend + Frontend Dev Server)
═════════════════════════════════════════════════════════════════════════════

Terminal 1 - Start Backend:
  cd d:\Project\AutoSaham
  python -m uvicorn src.api.server:app --host 127.0.0.1 --port 8000 --reload

Terminal 2 - Start Frontend Dev Server:
  cd d:\Project\AutoSaham\frontend
  npm run dev

Access:
  🎨 Frontend Dev: http://localhost:5173         (React with HMR)
  🌐 Backend API:  http://localhost:8000         (FastAPI)
  📊 Docs:         http://localhost:8000/docs    (Swagger API docs)

Use Case:
  ✅ Frontend development (hot reload)
  ✅ React component development
  ✅ Live CSS/JS editing


OPTION 3: ONE-COMMAND FULL STACK (Recommended)
═════════════════════════════════════════════════════════════════════════════

Windows (PowerShell):
  .\RUN_FULLSTACK.ps1

Windows (CMD):
  RUN_FULLSTACK.bat

Python (Any OS):
  python run_fullstack.py

What happens:
  ✅ Backend starts on :8000 (auto-reload enabled)
  ✅ Frontend dev server starts on :5173
  ✅ Both run in separate processes
  ✅ Hot reload enabled for both

Access:
  🎨 Frontend: http://localhost:5173
  🌐 Backend:  http://localhost:8000
  📊 UI:       http://localhost:8000/ui


═════════════════════════════════════════════════════════════════════════════

QUICK TEST COMMANDS (while running)
═════════════════════════════════════════════════════════════════════════════

Check backend health:
  curl http://localhost:8000/health

Get portfolio (real market data):
  curl http://localhost:8000/api/portfolio

Run ETL pipeline (fetch real IDX data):
  python -m src.main --run-etl --once --symbols BBCA USIM KLBF

Score stocks (real historical data):
  python scripts/select_stocks.py --symbols BBCA TLKM ASII

Trading demo (real prices):
  python -c "from src.demo import run_demo; run_demo(['BBCA', 'USIM', 'KLBF'])"


═════════════════════════════════════════════════════════════════════════════

ENVIRONMENT SETUP
═════════════════════════════════════════════════════════════════════════════

Auto-set by scripts:
  API_HOST = 127.0.0.1
  API_PORT = 8000
  MARKET_SYMBOLS = BBCA,USIM,KLBF,ASII,UNVR
  PYTHONUNBUFFERED = 1

Custom (optional):
  export MARKET_SYMBOLS="BBCA,TLKM,ASII"
  export API_PORT=9000
  export LOG_LEVEL=debug


═════════════════════════════════════════════════════════════════════════════

TROUBLESHOOTING
═════════════════════════════════════════════════════════════════════════════

Port already in use?
  • Change port: python -m uvicorn src.api.server:app --port 9000
  • Kill process: lsof -i :8000 (Linux) or Get-Process -Id (Get-NetTCPConnection).OwningProcess (Windows)

Frontend build issues?
  • Rebuild: cd frontend && npm run build
  • Clean: rm -rf frontend/dist && npm run build

Dependencies missing?
  • Backend: pip install -r requirements.txt
  • Frontend: cd frontend && npm install

API calls failing?
  • Check health: curl http://localhost:8000/health
  • Check logs: Look at terminal output for error messages
  • Real data delay: First fetch may take 10-30 seconds (Yahoo Finance API)


═════════════════════════════════════════════════════════════════════════════

TYPICAL WORKFLOW
═════════════════════════════════════════════════════════════════════════════

Development:
  1. Run: .\RUN_FULLSTACK.ps1
  2. Edit frontend code in src/ (auto-reload on :5173)
  3. Edit backend code in src/api/ (auto-reload on :8000)
  4. Test: Open http://localhost:5173

Production:
  1. Build frontend: cd frontend && npm run build
  2. Run: python -m src.main --api
  3. Access: http://localhost:8000/ui (serves built frontend)

Testing:
  1. Start backend only: python -m src.main --api
  2. Run tests: python -m pytest tests/
  3. Or use API directly: curl http://localhost:8000/api/...


═════════════════════════════════════════════════════════════════════════════

✅ Ready to run? Use: .\RUN_FULLSTACK.ps1 (PowerShell) or RUN_FULLSTACK.bat (CMD)

═════════════════════════════════════════════════════════════════════════════
