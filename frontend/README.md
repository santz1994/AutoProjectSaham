# AutoSaham UI (React + Vite)

Development:

```bash
cd frontend
npm install
npm run dev
```

This will start Vite dev server at http://localhost:5173 — use it alongside the FastAPI backend.

Production build (served by FastAPI):

```bash
cd frontend
npm run build
# then start the Python API server; it will serve the built files at /ui
python -m uvicorn src.api.server:app --host 127.0.0.1 --port 8000
```
