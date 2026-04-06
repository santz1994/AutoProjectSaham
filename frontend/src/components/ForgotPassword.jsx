/**
 * Forgot Password Page
 * Sends reset request and shows generic success response.
 */

import React, { useState } from 'react';
import Button from './Button';
import toast from '../store/toastStore';
import { getAPIBase } from '../utils/authService';
import './Auth.css';

export default function ForgotPassword({ onSwitchToLogin }) {
  const [email, setEmail] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [emailSent, setEmailSent] = useState(false);

  const validateEmail = (value) => {
    return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');

    if (!validateEmail(email)) {
      const message = 'Please enter a valid email address';
      setError(message);
      toast.error(message);
      return;
    }

    setLoading(true);
    try {
      const res = await fetch(`${getAPIBase()}/auth/forgot-password`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email }),
        credentials: 'include',
      });

      if (!res.ok) {
        const payload = await res.json().catch(() => ({}));
        const message = payload?.detail || 'Failed to send reset instructions';
        throw new Error(message);
      }

      const payload = await res.json().catch(() => ({}));
      toast.success(payload?.message || 'Reset instructions sent (if email exists).');
      setEmailSent(true);
    } catch (err) {
      const message = err?.message || 'Failed to send reset instructions';
      setError(message);
      toast.error(message);
    } finally {
      setLoading(false);
    }
  };

  if (emailSent) {
    return (
      <div className="auth-container">
        <div className="auth-card">
          <div className="auth-header">
            <div className="auth-logo success-icon">
              <span className="logo-icon">✅</span>
            </div>
            <h2>Check Your Email</h2>
            <p className="auth-subtitle">
              If an account exists for <strong>{email}</strong>, reset instructions have been sent.
            </p>
          </div>

          <div className="auth-form">
            <p style={{ color: '#94a3b8', marginBottom: '1.5rem', textAlign: 'center' }}>
              Did not receive the email? Check spam or try another address.
            </p>

            <Button variant="secondary" fullWidth onClick={() => setEmailSent(false)}>
              Try Different Email
            </Button>

            <div className="auth-footer">
              <button type="button" className="auth-link" onClick={onSwitchToLogin}>
                ← Back to Login
              </button>
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="auth-container">
      <div className="auth-card">
        <div className="auth-header">
          <div className="auth-logo">
            <span className="logo-icon">🤖</span>
            <span className="logo-text">AutoSaham</span>
          </div>
          <h2>Forgot Password?</h2>
          <p className="auth-subtitle">
            Enter your email and we will send password reset instructions.
          </p>
        </div>

        <form onSubmit={handleSubmit} className="auth-form">
          <div className="form-group">
            <label htmlFor="email">Email Address</label>
            <input
              id="email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className={error ? 'input-error' : ''}
              placeholder="Enter your email"
              autoFocus
              disabled={loading}
            />
            {error && <span className="error-message">{error}</span>}
          </div>

          <Button
            type="submit"
            variant="primary"
            fullWidth
            loading={loading}
            icon={<span>📧</span>}
            disabled={!email.trim()}
          >
            {loading ? 'Sending...' : 'Send Reset Instructions'}
          </Button>

          <div className="auth-footer">
            <button
              type="button"
              className="auth-link"
              onClick={onSwitchToLogin}
              disabled={loading}
            >
              ← Back to Login
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}