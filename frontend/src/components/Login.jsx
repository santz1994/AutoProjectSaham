import React, { useState } from 'react'
import '../styles/login.css'

export default function Login({ onLogin }) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState(null)
  const [isLoading, setIsLoading] = useState(false)

  async function submit(e) {
    e.preventDefault()
    setError(null)
    setIsLoading(true)

    try {
      const res = await fetch('/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password }),
      })

      if (res.ok) {
        const j = await res.json()
        localStorage.setItem('token', j.access_token)
        onLogin && onLogin(username)
        return
      }
    } catch (err) {
      // Backend not available - use demo mode
    }

    // Demo mode: Allow any non-empty username/password
    if (username.trim().length > 0 && password.length > 0) {
      localStorage.setItem('token', `demo_token_${Date.now()}`)
      onLogin && onLogin(username)
    } else {
      setError('Please enter username and password')
    }

    setIsLoading(false)
  }

  return (
    <div className="login-container">
      <div className="login-card">
        <div className="login-header">
          <div className="login-logo-icon">🤖</div>
          <h1>AutoSaham</h1>
          <p>AI-Powered Trading for Indonesia</p>
        </div>

        <form onSubmit={submit} className="login-form">
          <div className="form-group">
            <label htmlFor="username">Username or Email</label>
            <input
              id="username"
              type="text"
              placeholder="Enter your username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              disabled={isLoading}
            />
          </div>

          <div className="form-group">
            <label htmlFor="password">Password</label>
            <input
              id="password"
              type="password"
              placeholder="Enter your password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              disabled={isLoading}
            />
          </div>

          {error && <div className="error-message">{error}</div>}

          <button type="submit" className="login-btn" disabled={isLoading}>
            {isLoading ? 'Logging in...' : 'Login'}
          </button>

          <div className="login-footer">
            <small>Demo Mode: Enter any username & password to continue</small>
          </div>
        </form>
      </div>
    </div>
  )
}
