"""
Quick script to create a test user account
"""
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.api.auth import register_user

# Create test accounts
try:
    register_user('demo', 'demo123')
    print('✅ Created: demo / demo123')
except Exception as e:
    print(f'⚠️  demo account already exists or error: {e}')

try:
    register_user('admin', 'admin123')
    print('✅ Created: admin / admin123')
except Exception as e:
    print(f'⚠️  admin account already exists or error: {e}')

try:
    register_user('trader', 'trader123')
    print('✅ Created: trader / trader123')
except Exception as e:
    print(f'⚠️  trader account already exists or error: {e}')

try:
    register_user('test', 'test123')
    print('✅ Created: test / test123')
except Exception as e:
    print(f'⚠️  test account already exists or error: {e}')

print('\n📋 Available accounts:')
print('   Username: demo      | Password: demo123')
print('   Username: admin     | Password: admin123')
print('   Username: trader    | Password: trader123')
print('   Username: test      | Password: test123')
