"""Quick script to check server state - run via docker cp + docker exec."""
import os, sys, json

sys.path.insert(0, "/app")

print("PAPER_STARTING_CASH:", os.getenv("PAPER_STARTING_CASH", "NOT SET (default 100000000)"))
print()
print("Registered users:")
with open("/app/data/users.json") as f:
    users = json.load(f)
for username, data in users.items():
    role = data.get("role", "unknown")
    email = data.get("email", "none")
    print(f"  {username}: role={role}, email={email}")

print()
print("Portfolio env vars:")
for key in ["PAPER_STARTING_CASH", "AUTOSAHAM_ADMIN_USERS", "AUTOSAHAM_KILL_SWITCH_ADMIN_USERS"]:
    print(f"  {key}: {os.getenv(key, 'NOT SET')}")