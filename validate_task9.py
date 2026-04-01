#!/usr/bin/env python
"""
Final validation before moving to Task 10.
Checks all Task 9 deliverables are in place.
"""

import sys
from pathlib import Path
import json

print("=" * 70)
print("TASK 9 FINAL VALIDATION")
print("=" * 70)

checks = {
    "Core Implementation": {
        "src/ml/anomaly_detector.py": {
            "exists": False,
            "size_kb": 0,
            "contains": [
                "AutoencoderAnomaly",
                "AutoencoderDetector",
                "IsolationForestDetector",
                "StatisticalAnomalyDetector",
                "AnomalyRiskManager"
            ]
        }
    },
    "Tests": {
        "tests/test_anomaly_detection.py": {
            "exists": False,
            "size_kb": 0,
            "contains": [
                "TestIsolationForestDetector",
                "TestStatisticalAnomalyDetector",
                "TestAutoencoderDetector",
                "TestAnomalyRiskManager",
                "TestAnomalyDetectionIntegration"
            ]
        }
    },
    "Documentation": {
        "TASK9_SUMMARY.md": {
            "exists": False,
            "size_kb": 0
        }
    }
}

# Check files
base_path = Path("D:/Project/AutoSaham")

for category, files in checks.items():
    print(f"\n{category}:")
    print("-" * 70)
    
    for filename, config in files.items():
        filepath = base_path / filename
        
        if filepath.exists():
            size_kb = filepath.stat().st_size / 1024
            config["exists"] = True
            config["size_kb"] = size_kb
            
            # Check content if needed
            if "contains" in config:
                with open(filepath, 'r') as f:
                    content = f.read()
                    found_all = True
                    for keyword in config["contains"]:
                        if keyword not in content:
                            found_all = False
                            print(f"  ❌ {filename} - Missing: {keyword}")
                    
                    if found_all:
                        print(f"  ✅ {filename}")
                        print(f"     Size: {size_kb:.1f} KB")
                        print(f"     Contains: {len(config['contains'])} required components")
            else:
                print(f"  ✅ {filename}")
                print(f"     Size: {size_kb:.1f} KB")
        else:
            print(f"  ❌ {filename} - NOT FOUND")

# Summary
print("\n" + "=" * 70)
print("SUMMARY")
print("=" * 70)

total_checks = sum(1 for cat in checks.values() for _ in cat)
passed_checks = sum(
    1 for cat in checks.values() 
    for config in cat.values() 
    if config.get("exists")
)

print(f"\nFiles: {passed_checks}/{total_checks} ✅")

total_size = sum(
    sum(config.get("size_kb", 0) for config in cat.values())
    for cat in checks.values()
)

print(f"Total Size: {total_size:.1f} KB")

print("\n" + "=" * 70)
if passed_checks == total_checks:
    print("✅ ALL DELIVERABLES PRESENT - READY FOR TASK 10")
else:
    print(f"❌ {total_checks - passed_checks} files missing")
print("=" * 70)

sys.exit(0 if passed_checks == total_checks else 1)
