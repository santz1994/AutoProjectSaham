#!/usr/bin/env python3
"""
Local FastAPI Server Runner for Production Testing
Launches the AutoSaham API server locally without Docker
"""

import sys
import subprocess
from pathlib import Path

print("=" * 80)
print("AUTOSAHAM PRODUCTION SERVER - LOCAL MODE")
print("=" * 80)

# Check if uvicorn is available
try:
    import uvicorn
    print("\n[OK] Uvicorn installed")
except ImportError:
    print("\n[ERROR] Uvicorn not found")
    sys.exit(1)

# Check if FastAPI modules are available
try:
    from src.api import server
    print("[OK] FastAPI app loads successfully")
except ImportError as e:
    print(f"[ERROR] Failed to import FastAPI app: {e}")
    sys.exit(1)

print("\n" + "=" * 80)
print("STARTING API SERVER")
print("=" * 80)
print("\nServer will be available at:")
print("  - http://localhost:8000  (FastAPI)")
print("  - http://localhost:8001  (Kong Gateway - when available)")
print("\nEndpoints to test:")
print("  - POST http://localhost:8000/auth/register")
print("  - POST http://localhost:8000/auth/login")
print("  - POST http://localhost:8000/auth/forgot-password")
print("  - GET  http://localhost:8000/api/portfolio")
print("  - GET  http://localhost:8000/api/bot/status")
print("\nPress Ctrl+C to stop the server")
print("\n" + "=" * 80)

uvicorn.run(
    "src.api.server:app",
    host="0.0.0.0",
    port=8000,
    reload=False,
    log_level="info"
)
