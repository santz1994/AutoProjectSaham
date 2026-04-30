"""Entry point for running the API server via: python -m src.api.server

SECURITY: This server binds to 127.0.0.1:8000 by default.
For production internet exposure, deploy behind a reverse proxy (nginx/caddy).
"""
import uvicorn

if __name__ == "__main__":
    # SECURITY FIX: Default to localhost; reverse proxy handles external traffic
    uvicorn.run(
        "src.api.server:app",
        host="127.0.0.1",
        port=8000,
        reload=False,
        log_level="info"
    )
