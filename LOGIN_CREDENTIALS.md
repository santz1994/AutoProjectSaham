# 🔐 AutoSaham Test Accounts

## Available Accounts

### Account 1: Demo (Already Exists)
- **Username**: `demo`
- **Password**: `demo`
- **Status**: ✅ Active

### Account 2: Admin (Create this if needed)
- **Username**: `admin`
- **Password**: `admin123`
- **Status**: Create using script below

### Account 3: Trader (Create this if needed)
- **Username**: `trader`
- **Password**: `trader123`
- **Status**: Create using script below

---

## How to Create New Accounts

### Option 1: Use the Registration Page
1. Start the app: `npm run dev` in frontend folder
2. Click "Register here" link on login page
3. Fill in username and password
4. Click "Create Account"

### Option 2: Use Python Script
```bash
cd D:\Project\AutoSaham
python scripts\create_test_users.py
```

### Option 3: Use Python Directly
```bash
cd D:\Project\AutoSaham
python -c "from src.api.auth import register_user; register_user('myusername', 'mypassword'); print('Account created!')"
```

---

## Quick Login

**Recommended for Testing:**
- Username: `demo`
- Password: `demo`

This account already exists and you can login immediately!

---

## User Database Location

**File**: `D:\Project\AutoSaham\data\users.json`

This file contains all registered users with hashed passwords (PBKDF2 + salt).

---

## Testing the App

1. **Start Backend**:
   ```bash
   cd D:\Project\AutoSaham
   python -m src.main --api
   ```
   Server runs on: http://127.0.0.1:8000

2. **Start Frontend**:
   ```bash
   cd D:\Project\AutoSaham\frontend
   npm run dev
   ```
   App runs on: http://localhost:5173

3. **Login**:
   - Open browser to http://localhost:5173
   - Enter username: `demo`
   - Enter password: `demo`
   - Click "Login"

---

## What You Can Do After Login

✅ View real-time dashboard with portfolio data
✅ Check bot status and trading signals
✅ View market intelligence and sentiment
✅ Review trading strategies
✅ Check trade logs and history
✅ Monitor portfolio health score
✅ See recent trading activity
✅ Generate performance reports

---

## Need Help?

- **Forgot Password?** Click "Forgot password?" link on login page
- **Want New Account?** Click "Register here" on login page
- **API Not Working?** Make sure backend server is running on port 8000

---

**Current Time**: 2026-04-02

**Ready to trade!** 🚀📈
