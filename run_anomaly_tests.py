#!/usr/bin/env python
"""Quick test runner for anomaly detection."""

import sys
import subprocess

result = subprocess.run(
    [sys.executable, "-m", "pytest", "tests/test_anomaly_detection.py", "-v", "--tb=short"],
    cwd="D:\\Project\\AutoSaham"
)

sys.exit(result.returncode)
