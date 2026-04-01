#!/usr/bin/env python
"""Quick git status checker"""
import subprocess
import sys

try:
    result = subprocess.run(
        ["git", "status", "--short"],
        cwd="D:\\Project\\AutoSaham",
        capture_output=True,
        text=True,
        timeout=10
    )
    
    print("=" * 70)
    print("GIT STATUS - TASK 9 CHANGES")
    print("=" * 70)
    print(result.stdout)
    
    if result.returncode == 0:
        print("\n✅ Git repository is accessible")
    else:
        print(f"\n⚠️  Git status error: {result.stderr}")
        
except Exception as e:
    print(f"⚠️  Could not check git status: {e}")
