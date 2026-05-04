"""
Quick script to create a test user account
"""
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.api.auth import register_user

accounts = [
    ('demo', 'demo123'),
    ('admin', 'admin123'),
    ('trader', 'trader123'),
    ('test', 'test123'),
]

for username, password in accounts:
    try:
        register_user(username, password)
        print(f'[OK] Created: {username} / {password}')
    except RuntimeError as e:
        if 'exists' in str(e):
            print(f'[SKIP] {username} already exists')
        else:
            print(f'[ERR] {username}: {e}')
    except Exception as e:
        print(f'[ERR] {username}: {e}')

print()
print('Available accounts:')
for username, password in accounts:
    print(f'  Username: {username:<10} | Password: {password}')
