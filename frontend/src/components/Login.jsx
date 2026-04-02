import React, { useState } from 'react'
import AuthService from '../utils/authService'
import Button from './Button'
import toast from '../store/toastStore'
import './Auth.css'

export default function Login({ onLogin, onSwitchToRegister, onSwitchToForgotPassword }) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState(null)
  const [isLoading, setIsLoading] = useState(false)
  const [rememberMe, setRememberMe] = useState(false)

  async function submit(e) {
    e.preventDefault()
    setError(null)
    setIsLoading(true)

    try {
      // SECURITY FIX: Use AuthService which handles httpOnly cookies securely
      const result = await AuthService.login(username, password)
      
      if (result.ok) {
        toast.success(`Welcome back, ${username}! 🎉`)
        onLogin && onLogin(username)
        return
      } else {
        const errorMsg = result.error || 'Login failed'
        setError(errorMsg)
        toast.error(errorMsg)
      }
    } catch (err) {
      const errorMsg = 'Network error: ' + err.message
      setError(errorMsg)
      toast.error(errorMsg)
    }

    setIsLoading(false)
  }

  return (
    <div className="auth-container">
      <div className="auth-card">
        <div className="auth-header">
          <div className="auth-logo">
            <span className="logo-icon">🤖</span>
            <span className="logo-text">AutoSaham</span>
          </div>
          <h2>Welcome Back</h2>
          <p className="auth-subtitle">Login to your AutoSaham account</p>
        </div>

        <form onSubmit={submit} className="auth-form">
          <div className="form-group">
            <label htmlFor="username">Username</label>
            <input
              id="username"
              type="text"
              placeholder="Enter your username"
              autoComplete="username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              disabled={isLoading}
              autoFocus
            />
          </div>

          <div className="form-group">
            <label htmlFor="password">Password</label>
            <input
              id="password"
              type="password"
              placeholder="Enter your password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              disabled={isLoading}
            />
          </div>

          <div className="form-checkbox">
            <input
              id="rememberMe"
              type="checkbox"
              checked={rememberMe}
              onChange={(e) => setRememberMe(e.target.checked)}
            />
            <label htmlFor="rememberMe">Remember me</label>
          </div>

          {error && <div className="error-message">{error}</div>}

          <Button
            type="submit"
            variant="primary"
            fullWidth
            loading={isLoading}
            icon={<span>🔑</span>}
          >
            {isLoading ? 'Logging in...' : 'Login'}
          </Button>

          {onSwitchToForgotPassword && (
            <div className="auth-footer" style={{ marginTop: '1rem' }}>
              <button
                type="button"
                className="auth-link"
                onClick={onSwitchToForgotPassword}
              >
                Forgot password?
              </button>
            </div>
          )}

          {onSwitchToRegister && (
            <div className="auth-footer">
              <p>
                Don't have an account?{' '}
                <button
                  type="button"
                  className="auth-link"
                  onClick={onSwitchToRegister}
                >
                  Register here
                </button>
              </p>
            </div>
          )}
        </form>
      </div>
    </div>
  )
}
