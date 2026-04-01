"""
QuickStart Script for AutoSaham

One-command startup for the entire platform:
1. Check environment
2. Fetch market data (if needed)
3. Train model (if needed)
4. Start API server
5. Instructions for frontend

Usage:
    python scripts/quickstart.py
"""
import sys
import subprocess
import time
from pathlib import Path


def run_command(cmd: list, description: str, check: bool = True):
    """Run a command and print status."""
    print(f"\n{'='*60}")
    print(f"▶ {description}")
    print(f"{'='*60}")
    
    try:
        result = subprocess.run(cmd, check=check)
        if result.returncode == 0:
            print(f"✓ {description} - SUCCESS\n")
            return True
        else:
            print(f"✗ {description} - FAILED\n")
            return False
    except Exception as e:
        print(f"✗ {description} - ERROR: {e}\n")
        return False


def main():
    """Main quickstart function."""
    project_root = Path(__file__).parent.parent
    
    print("""
╔═══════════════════════════════════════════════════════════╗
║                                                           ║
║           🚀 AutoSaham QuickStart 🚀                     ║
║                                                           ║
║   Starting all services...                               ║
║                                                           ║
╚═══════════════════════════════════════════════════════════╝
    """)
    
    # Step 1: Check .env
    env_file = project_root / '.env'
    if not env_file.exists():
        print("⚠ .env file not found!")
        print("Running setup wizard first...\n")
        run_command([sys.executable, 'scripts/setup_wizard.py'], "Setup Wizard")
    
    # Step 2: Test triple-barrier implementation
    print("\n📊 Testing Triple-Barrier Labeling...")
    run_command(
        [sys.executable, '-m', 'src.ml.barriers'],
        "Triple-Barrier Test",
        check=False
    )
    
    # Step 3: Check for data
    data_dir = project_root / 'data' / 'prices'
    if not data_dir.exists() or not list(data_dir.glob('*.json')):
        print("\n📈 Fetching market data...")
        run_command(
            [sys.executable, '-m', 'src.main', '--run-etl', '--symbols', 'BBCA', 'TLKM', 'ASII', '--once'],
            "Fetch Market Data",
            check=False
        )
    else:
        print("\n✓ Market data already exists")
    
    # Step 4: Check for model
    models_dir = project_root / 'models'
    model_file = models_dir / 'model.joblib'
    
    if not model_file.exists():
        print("\n🧠 Training ML model...")
        run_command(
            [sys.executable, 'scripts/train_model.py', '--limit', '20'],
            "Train ML Model",
            check=False
        )
    else:
        print("\n✓ ML model already trained")
    
    # Step 5: Start API server
    print("\n🌐 Starting API server...")
    print("   API will be available at: http://localhost:8000")
    print("   API docs at: http://localhost:8000/docs")
    print("\n   Press Ctrl+C to stop\n")
    
    try:
        subprocess.run([
            sys.executable,
            '-m',
            'uvicorn',
            'src.api.server:app',
            '--host',
            '0.0.0.0',
            '--port',
            '8000',
            '--reload'
        ])
    except KeyboardInterrupt:
        print("\n\n✓ Server stopped")
    
    # Instructions for frontend
    print("""
    
╔═══════════════════════════════════════════════════════════╗
║                                                           ║
║   To start the frontend (in a new terminal):             ║
║                                                           ║
║   cd frontend                                             ║
║   npm install                                             ║
║   npm run dev                                             ║
║                                                           ║
║   Frontend will be at: http://localhost:5173             ║
║                                                           ║
╚═══════════════════════════════════════════════════════════╝
    """)


if __name__ == "__main__":
    main()
