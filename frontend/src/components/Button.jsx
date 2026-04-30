/**
 * Enhanced Button Component
 * Supports multiple variants, states, sizes, and icons
 */

import React from 'react';
import './Button.css';

const Button = ({
  children,
  variant = 'primary',
  size = 'md',
  disabled = false,
  loading = false,
  success = false,
  error = false,
  icon = null,
  iconPosition = 'left',
  fullWidth = false,
  onClick,
  type = 'button',
  className = '',
  title = '',
  ariaLabel = '',
  ...props
}) => {
  const buttonClasses = [
    'btn',
    `btn-${variant}`,
    `btn-${size}`,
    loading && 'btn-loading',
    success && 'btn-success-state',
    error && 'btn-error-state',
    disabled && 'btn-disabled',
    fullWidth && 'btn-full-width',
    className,
  ]
    .filter(Boolean)
    .join(' ');

  const handleClick = (e) => {
    if (disabled || loading) {
      e.preventDefault();
      return;
    }
    onClick?.(e);
  };

  return (
    <button
      type={type}
      className={buttonClasses}
      onClick={handleClick}
      disabled={disabled || loading}
      title={title}
      aria-label={ariaLabel || title}
      aria-busy={loading}
      aria-disabled={disabled}
      {...props}
    >
      {loading && (
        <span className="btn-spinner" aria-hidden="true">
          <svg viewBox="0 0 24 24" className="spinner-icon">
            <circle
              className="spinner-circle"
              cx="12"
              cy="12"
              r="10"
              fill="none"
              strokeWidth="3"
            />
          </svg>
        </span>
      )}
      
      {!loading && icon && iconPosition === 'left' && (
        <span className="btn-icon btn-icon-left" aria-hidden="true">
          {icon}
        </span>
      )}
      
      <span className="btn-content">{children}</span>
      
      {!loading && icon && iconPosition === 'right' && (
        <span className="btn-icon btn-icon-right" aria-hidden="true">
          {icon}
        </span>
      )}
      
      {success && (
        <span className="btn-success-icon" aria-hidden="true">
          ✓
        </span>
      )}
      
      {error && (
        <span className="btn-error-icon" aria-hidden="true">
          ✕
        </span>
      )}
    </button>
  );
};

export default Button;
