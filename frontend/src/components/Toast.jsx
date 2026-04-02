/**
 * Toast Container Component
 * Renders all active toast notifications
 */

import React, { useEffect } from 'react';
import { useToastStore } from '../store/toastStore';
import './Toast.css';

const Toast = ({ id, message, type, action, onClose }) => {
  const icons = {
    success: '✓',
    error: '✕',
    warning: '⚠',
    info: 'ℹ',
    loading: '⟳',
  };

  return (
    <div className={`toast toast-${type}`} role="alert" aria-live="polite">
      <div className="toast-icon" aria-hidden="true">
        {icons[type] || icons.info}
      </div>
      
      <div className="toast-content">
        <p className="toast-message">{message}</p>
        {action && (
          <button
            className="toast-action"
            onClick={() => {
              action.onClick();
              onClose();
            }}
          >
            {action.label}
          </button>
        )}
      </div>
      
      <button
        className="toast-close"
        onClick={onClose}
        aria-label="Close notification"
        title="Close"
      >
        ×
      </button>
    </div>
  );
};

const ToastContainer = () => {
  const { toasts, removeToast } = useToastStore();

  // Announce to screen readers
  useEffect(() => {
    if (toasts.length > 0) {
      const latestToast = toasts[toasts.length - 1];
      const announcement = document.getElementById('toast-announcer');
      if (announcement) {
        announcement.textContent = `${latestToast.type}: ${latestToast.message}`;
      }
    }
  }, [toasts]);

  return (
    <>
      {/* Screen reader announcer */}
      <div
        id="toast-announcer"
        className="sr-only"
        role="status"
        aria-live="polite"
        aria-atomic="true"
      />
      
      {/* Toast container */}
      <div className="toast-container" aria-label="Notifications">
        {toasts.map((toast) => (
          <Toast
            key={toast.id}
            {...toast}
            onClose={() => removeToast(toast.id)}
          />
        ))}
      </div>
    </>
  );
};

export default ToastContainer;
