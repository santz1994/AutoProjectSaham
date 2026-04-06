/**
 * Forgot Password Page
 * Allows users to request a password reset
 */

import React, { useState } from 'react';
import Button from './Button';
import toast from '../store/toastStore';
import { getAPIBase } from '../utils/authService';
import './Auth.css';

export default function ForgotPassword({ onSwitchToLogin }) {
  const [email, setEmail] = useState('');
  const [loading, setLoading] = useState(false);
  const [emailSent, setEmailSent] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();

    if (!email || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
      toast.error('Please enter a valid email address');
      return;
    }

    try {
      setLoading(true);
      
      // Call password reset API
      const response = await fetch(`${getAPIBase()}/auth/forgot-password`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email }),
        credentials: 'include',
      });

      if (!response.ok) {
        throw new Error('Password reset failed');
      }

      setEmailSent(true);
      toast.success('Password reset instructions sent to your email!');
    } catch (error) {
      toast.error('Failed to send reset email. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  if (emailSent) {
    return (
      <div className="auth-card">
        <div className="auth-header">
          <div className="success-icon" style={{ fontSize: '4rem', marginBottom: '1rem' }}>
            ✅
          </div>
          <h2>Check Your Email</h2>
          <p className="auth-subtitle">
            We've sent password reset instructions to <strong>{email}</strong>
          </p>
        </div>

        <div className="auth-form">
          <p style={{ color: '#94a3b8', marginBottom: '1.5rem', textAlign: 'center' }}>
            Didn't receive the email? Check your spam folder or try again.
          </p>

          <Button
            variant="secondary"
            fullWidth
            onClick={() => setEmailSent(false)}
          >
            Try Different Email
          </Button>

          <div className="auth-footer">
            <button
              type="button"
              className="auth-link"
              onClick={onSwitchToLogin}
            >
              ← Back to Login
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="auth-card">
      <div className="auth-header">
        <div className="auth-logo">
          <span className="logo-icon">🤖</span>
          <span className="logo-text">AutoSaham</span>
        </div>
        <h2>Forgot Password?</h2>
        <p className="auth-subtitle">
          Enter your email and we'll send you instructions to reset your password
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
            placeholder="Enter your email"
            autoFocus
          />
        </div>

        <Button
          type="submit"
          variant="primary"
          fullWidth
          loading={loading}
          icon={<span>📧</span>}
        >
          {loading ? 'Sending...' : 'Send Reset Instructions'}
        </Button>

        <div className="auth-footer">
          <button
            type="button"
            className="auth-link"
            onClick={onSwitchToLogin}
          >
            ← Back to Login
          </button>
        </div>
      </form>
    </div>
  );
}
