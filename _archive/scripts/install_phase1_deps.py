"""
Quick dependency installer for Phase 1 integration testing.

This script installs only the essential dependencies needed to run
Phase 1 integration tests without installing all packages.

Usage:
    python scripts/install_phase1_deps.py
"""
import subprocess
import sys


def install_package(package: str) -> bool:
    """Install a Python package using pip."""
    try:
        print(f"Installing {package}...")
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", package],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        print(f"✅ {package} installed successfully")
        return True
    except subprocess.CalledProcessError:
        print(f"❌ Failed to install {package}")
        return False


def main():
    """Install Phase 1 dependencies."""
    print("\n" + "="*60)
    print("Phase 1 Dependency Installer")
    print("="*60 + "\n")
    
    # Essential Phase 1 dependencies
    dependencies = [
        "vaderSentiment>=3.3.2",
        "scipy>=1.10.0",
        "lightgbm>=3.3.5",
        # These are likely already installed, but include for completeness
        "scikit-learn>=1.0.0",
        "pandas>=1.5.0",
        "numpy>=1.24.0"
    ]
    
    print("Installing essential dependencies for Phase 1 testing...\n")
    
    results = []
    for dep in dependencies:
        success = install_package(dep)
        results.append((dep, success))
    
    # Summary
    print("\n" + "="*60)
    print("Installation Summary")
    print("="*60 + "\n")
    
    success_count = sum(1 for _, success in results if success)
    total = len(results)
    
    for dep, success in results:
        status = "✅" if success else "❌"
        print(f"{status} {dep}")
    
    print(f"\n{success_count}/{total} packages installed successfully")
    
    if success_count == total:
        print("\n🎉 All dependencies installed! You can now run:")
        print("   python tests/integration/test_phase1_integration.py")
    else:
        print("\n⚠️  Some packages failed to install.")
        print("   Try installing manually: pip install -r requirements.txt")
    
    print()


if __name__ == "__main__":
    main()
