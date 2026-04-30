import time
import urllib.request
import sys

url = "http://127.0.0.1:8000/health"
for i in range(20):
    try:
        with urllib.request.urlopen(url, timeout=2) as resp:
            data = resp.read().decode()
            print("OK", data)
            sys.exit(0)
    except Exception as e:
        print(f"attempt {i+1} failed: {e}")
        time.sleep(0.5)

print("FAILED to reach server")
sys.exit(2)
