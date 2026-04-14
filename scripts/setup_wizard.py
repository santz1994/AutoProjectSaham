"""
Interactive Setup Wizard for AutoSaham

Run this script for first-time setup:
    python scripts/setup_wizard.py

Goal: Reduce setup time from 30 minutes to <5 minutes.
"""
from __future__ import annotations

import os
import sys
import subprocess
import platform
from pathlib import Path
from typing import Dict


class Colors:
    """ANSI color codes for terminal output."""
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'


class SetupWizard:
    """Interactive setup wizard for AutoSaham."""
    
    def __init__(self):
        """Initialize setup wizard."""
        self.project_root = Path(__file__).parent.parent
        self.env_file = self.project_root / '.env'
        self.requirements_file = self.project_root / 'requirements.txt'
        
    def print_header(self, text: str) -> None:
        """Print formatted header."""
        print(f"\n{Colors.HEADER}{Colors.BOLD}{'='*60}{Colors.ENDC}")
        print(f"{Colors.HEADER}{Colors.BOLD}{text.center(60)}{Colors.ENDC}")
        print(f"{Colors.HEADER}{Colors.BOLD}{'='*60}{Colors.ENDC}\n")
    
    def print_success(self, text: str) -> None:
        """Print success message."""
        print(f"{Colors.OKGREEN}✓ {text}{Colors.ENDC}")
    
    def print_warning(self, text: str) -> None:
        """Print warning message."""
        print(f"{Colors.WARNING}⚠ {text}{Colors.ENDC}")
    
    def print_error(self, text: str) -> None:
        """Print error message."""
        print(f"{Colors.FAIL}✗ {text}{Colors.ENDC}")
    
    def print_info(self, text: str) -> None:
        """Print info message."""
        print(f"{Colors.OKCYAN}ℹ {text}{Colors.ENDC}")
    
    def ask_yes_no(self, question: str, default: bool = True) -> bool:
        """Ask yes/no question."""
        default_str = "Y/n" if default else "y/N"
        response = input(f"{Colors.OKBLUE}? {question} [{default_str}]: {Colors.ENDC}").strip().lower()
        
        if not response:
            return default
        return response in ['y', 'yes']
    
    def ask_input(self, question: str, default: str = "", required: bool = False) -> str:
        """Ask for text input."""
        while True:
            default_display = f" [{default}]" if default else ""
            response = input(f"{Colors.OKBLUE}? {question}{default_display}: {Colors.ENDC}").strip()
            
            if not response:
                if default:
                    return default
                elif not required:
                    return ""
                else:
                    self.print_error("This field is required!")
                    continue
            
            return response
    
    def check_python_version(self) -> bool:
        """Check if Python version is compatible."""
        self.print_header("Step 1: Python Version Check")
        
        version = sys.version_info
        version_str = f"{version.major}.{version.minor}.{version.micro}"
        
        self.print_info(f"Python version: {version_str}")
        self.print_info(f"Platform: {platform.system()} {platform.release()}")
        
        if version.major < 3 or (version.major == 3 and version.minor < 8):
            self.print_error("Python 3.8+ required!")
            return False
        
        if version.major == 3 and version.minor < 11:
            self.print_warning("Python 3.11+ recommended for best performance")
        else:
            self.print_success(f"Python {version_str} is compatible!")
        
        return True
    
    def check_dependencies(self) -> Dict[str, bool]:
        """Check which dependencies are installed."""
        self.print_header("Step 2: Dependency Check")
        
        dependencies = {
            'numpy': 'numpy',
            'pandas': 'pandas',
            'requests': 'requests',
            'fastapi': 'fastapi',
            'scikit-learn': 'sklearn',
            'lightgbm': 'lightgbm',
        }
        
        results = {}
        
        for name, import_name in dependencies.items():
            try:
                __import__(import_name)
                self.print_success(f"{name} is installed")
                results[name] = True
            except ImportError:
                self.print_warning(f"{name} is NOT installed")
                results[name] = False
        
        missing_count = sum(1 for installed in results.values() if not installed)
        
        if missing_count > 0:
            self.print_info(f"\n{missing_count} packages need to be installed")
        else:
            self.print_success("\nAll core dependencies are installed!")
        
        return results
    
    def install_dependencies(self) -> bool:
        """Install missing dependencies."""
        self.print_header("Step 3: Installing Dependencies")
        
        if not self.requirements_file.exists():
            self.print_error(f"requirements.txt not found")
            return False
        
        install = self.ask_yes_no("Install/upgrade all dependencies?", default=True)
        
        if not install:
            self.print_warning("Skipping dependency installation")
            return True
        
        self.print_info("Installing dependencies... (this may take a few minutes)")
        
        try:
            subprocess.check_call([
                sys.executable, 
                '-m', 
                'pip', 
                'install', 
                '-r', 
                str(self.requirements_file),
                '--upgrade'
            ])
            
            self.print_success("Dependencies installed successfully!")
            return True
            
        except subprocess.CalledProcessError as e:
            self.print_error(f"Failed to install dependencies: {e}")
            return False
    
    def configure_environment(self) -> bool:
        """Configure environment variables."""
        self.print_header("Step 4: Environment Configuration")
        
        if self.env_file.exists():
            overwrite = self.ask_yes_no(".env already exists. Overwrite?", default=False)
            if not overwrite:
                self.print_info("Using existing .env file")
                return True
        
        # NewsAPI Key
        self.print_info("\n📰 NewsAPI (optional - for news sentiment)")
        self.print_info("Get free key at: https://newsapi.org/")
        newsapi_key = self.ask_input("NewsAPI key", default="", required=False)
        
        # Market symbols
        self.print_info("\n📊 Default symbols to trade")
        default_symbols = "EURUSD=X,GBPUSD=X,BTC-USD,ETH-USD"
        symbols = self.ask_input("Market symbols (comma-separated)", default=default_symbols)
        
        # Create .env content
        env_content = f"""# AutoSaham Environment Configuration

# API Keys
NEWSAPI_KEY={newsapi_key}

# Market Configuration
MARKET_SYMBOLS={symbols}

# Database Paths
TICKS_DB_PATH=data/ticks.db
ETL_DB_PATH=data/etl.db

# Model Configuration
MODELS_DIR=models
ML_TRAIN_INTERVAL=86400

# API Configuration
API_HOST=0.0.0.0
API_PORT=8000
"""
        
        # Write .env file
        try:
            self.env_file.write_text(env_content, encoding='utf-8')
            self.print_success(".env file created!")
            return True
        except Exception as e:
            self.print_error(f"Failed to create .env: {e}")
            return False
    
    def initialize_directories(self) -> bool:
        """Create necessary directories."""
        self.print_header("Step 5: Directory Initialization")
        
        directories = [
            'data/prices',
            'data/dataset',
            'data/features',
            'models',
            'logs'
        ]
        
        for dir_path in directories:
            full_path = self.project_root / dir_path
            try:
                full_path.mkdir(parents=True, exist_ok=True)
                self.print_success(f"Created: {dir_path}/")
            except Exception as e:
                self.print_error(f"Failed to create {dir_path}: {e}")
                return False
        
        self.print_success("All directories created!")
        return True
    
    def show_next_steps(self) -> None:
        """Show next steps after setup."""
        self.print_header("🚀 Next Steps")
        
        print(f"""
{Colors.OKGREEN}Setup complete! Here's what you can do next:{Colors.ENDC}

1. {Colors.BOLD}Test triple-barrier labeling:{Colors.ENDC}
   python -m src.ml.barriers

2. {Colors.BOLD}Fetch market data:{Colors.ENDC}
    python -m src.main --run-etl --symbols EURUSD=X BTC-USD

3. {Colors.BOLD}Train ML model:{Colors.ENDC}
   python scripts/train_model.py --limit 50

4. {Colors.BOLD}Start API server:{Colors.ENDC}
   python -m uvicorn src.api.server:app --reload

{Colors.OKCYAN}📚 Documentation:{Colors.ENDC}
   - README.md - Project overview
   - PROGRESS.md - Implementation progress

{Colors.BOLD}Happy trading! 📈{Colors.ENDC}
        """)
    
    def run(self) -> bool:
        """Run the complete setup wizard."""
        print(f"""
{Colors.HEADER}{Colors.BOLD}
╔═══════════════════════════════════════════════════════════╗
║                                                           ║
║           🚀 AutoSaham Setup Wizard 🚀                   ║
║                                                           ║
║   Automated Trading Platform for Forex/Crypto            ║
║                                                           ║
╚═══════════════════════════════════════════════════════════╝
{Colors.ENDC}

{Colors.OKCYAN}This wizard will guide you through setup.
It should take less than 5 minutes.{Colors.ENDC}
        """)
        
        # Step 1: Python version
        if not self.check_python_version():
            return False
        
        # Step 2: Check dependencies
        dep_status = self.check_dependencies()
        
        # Step 3: Install dependencies
        if not all(dep_status.values()):
            if not self.install_dependencies():
                self.print_warning("Continuing with partial dependencies...")
        
        # Step 4: Configure environment
        if not self.configure_environment():
            return False
        
        # Step 5: Initialize directories
        if not self.initialize_directories():
            return False
        
        # Show next steps
        self.show_next_steps()
        
        return True


def main():
    """Main entry point."""
    wizard = SetupWizard()
    
    try:
        success = wizard.run()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print(f"\n\n{Colors.WARNING}Setup cancelled by user{Colors.ENDC}")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n{Colors.FAIL}Setup failed: {e}{Colors.ENDC}")
        sys.exit(1)


if __name__ == "__main__":
    main()
