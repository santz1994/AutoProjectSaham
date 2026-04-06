/**
 * PWA Update Notification Component
 * Shows when a new version is available
 */
import React from 'react';
import Button from './Button';
import './UpdateNotification.css';

export default function UpdateNotification({ onUpdate, onDismiss }) {
  return (
    <div className="update-notification">
      <div className="update-notification-content">
        <div className="update-icon">🚀</div>
        <div className="update-text">
          <h4>Update Available</h4>
          <p>A new version of AutoSaham is ready</p>
        </div>
        <div className="update-actions">
          <Button
            variant="primary"
            size="sm"
            onClick={onUpdate}
          >
            Update Now
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={onDismiss}
          >
            Later
          </Button>
        </div>
      </div>
    </div>
  );
}
