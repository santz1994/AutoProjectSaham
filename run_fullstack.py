#!/usr/bin/env python3
"""
AutoSaham Full Stack Launcher
==============================
Runs both backend API and frontend build in one command
"""
import subprocess
import os
import sys
import threading
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.absolute()

def run_backend():
    """Start FastAPI backend server"""
    print("\n" + "="*70)
    print("🚀 STARTING BACKEND (FastAPI)")
    print("="*70)
    print("📍 URL: http://127.0.0.1:8000")
    print("📍 Health: http://127.0.0.1:8000/health")
    print("📍 UI: http://127.0.0.1:8000/ui")
    print("="*70 + "\n")
    
    os.chdir(PROJECT_ROOT)
    env = os.environ.copy()
    env.update({
        "API_HOST": "127.0.0.1",
        "API_PORT": "8000",
        "MARKET_SYMBOLS": "BBCA,USIM,KLBF,ASII,UNVR",
        "PYTHONUNBUFFERED": "1"
    })
    
    subprocess.run(
        [sys.executable, "-m", "uvicorn", "src.api.server:app", 
         "--host", "127.0.0.1", "--port", "8000", "--reload"],
        env=env
    )

def run_frontend():
    """Start Vite dev server for frontend"""
    print("\n" + "="*70)
    print("🎨 STARTING FRONTEND (Vite Dev Server)")
    print("="*70)
    print("📍 URL: http://127.0.0.1:5173")
    print("⏳ Waiting for backend to start on :8000...")
    print("="*70 + "\n")
    
    # Wait a bit for backend to start
    time.sleep(3)
    
    frontend_dir = PROJECT_ROOT / "frontend"
    os.chdir(frontend_dir)
    subprocess.run(["npm", "run", "dev"])

def main():
    """Run both backend and frontend"""
    print("\n" + "="*70)
    print("✨ AutoSaham Full Stack - Starting...")
    print("="*70)
    
    # Start backend in background thread
    backend_thread = threading.Thread(target=run_backend, daemon=False)
    backend_thread.start()
    
    # Give backend a moment to start
    time.sleep(2)
    
    # Start frontend in main thread
    run_frontend()

if __name__ == "__main__":
    main()
