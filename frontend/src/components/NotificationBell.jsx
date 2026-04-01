/**
 * NotificationBell - Notification indicator component
 * Displays unread notification count with badge
 * Opens notification panel on click
 * Jakarta timezone (WIB: UTC+7) aware
 */

import React, { useState, useEffect } from 'react';
import useNotifications from '../hooks/useNotifications';
import NotificationCenter from './NotificationCenter';
import './NotificationBell.css';

export const NotificationBell = ({ userId, position = 'top-right' }) => {
  const [isOpen, setIsOpen] = useState(false);
  const {
    unreadCount,
    notifications,
    isConnected,
    markAsRead,
    markAllAsRead,
    error,
  } = useNotifications(userId);

  const handleBellClick = () => {
    setIsOpen(!isOpen);
    
    // Auto-mark visible notifications as read after 1 second
    if (!isOpen) {
      setTimeout(() => {
        notifications
          .filter((n) => !n.read)
          .slice(0, 5)
          .forEach((n) => markAsRead(n.id));
      }, 1000);
    }
  };

  const handleMarkAllAsRead = (e) => {
    e.stopPropagation();
    markAllAsRead();
  };

  return (
    <div className={`notification-bell-container ${position}`}>
      {/* Connection Status Indicator */}
      <div className={`ws-indicator ${isConnected ? 'connected' : 'disconnected'}`} 
           title={isConnected ? 'Connected' : 'Disconnected'}>
      </div>

      {/* Bell Button */}
      <button
        className={`notification-bell ${unreadCount > 0 ? 'has-unread' : ''}`}
        onClick={handleBellClick}
        aria-label={`Notifications (${unreadCount} unread)`}
        title={`${unreadCount} unread notifications`}
      >
        <svg
          className="bell-icon"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"></path>
          <path d="M13.73 21a2 2 0 0 1-3.46 0"></path>
        </svg>

        {/* Unread Badge */}
        {unreadCount > 0 && (
          <span className="unread-badge">
            {unreadCount > 99 ? '99+' : unreadCount}
          </span>
        )}
      </button>

      {/* Notification Panel */}
      {isOpen && (
        <div className="notification-panel" onClick={(e) => e.stopPropagation()}>
          {/* Panel Header */}
          <div className="notification-panel-header">
            <h3>Notifications</h3>
            {unreadCount > 0 && (
              <button
                className="mark-all-read-btn"
                onClick={handleMarkAllAsRead}
                title="Mark all as read"
              >
                Mark all as read
              </button>
            )}
          </div>

          {/* Connection Status */}
          {!isConnected && (
            <div className="connection-warning">
              <svg viewBox="0 0 24 24" fill="currentColor">
                <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 18c-4.42 0-8-3.58-8-8s3.58-8 8-8 8 3.58 8 8-3.58 8-8 8zm3.5-9c.83 0 1.5-.67 1.5-1.5S16.33 8 15.5 8 14 8.67 14 9.5s.67 1.5 1.5 1.5zm-7 0c.83 0 1.5-.67 1.5-1.5S9.33 8 8.5 8 7 8.67 7 9.5 7.67 11 8.5 11zm3.5 6.5c2.33 0 4.31-1.46 5.11-3.5H6.89c.8 2.04 2.78 3.5 5.11 3.5z" />
              </svg>
              <span>Reconnecting...</span>
            </div>
          )}

          {/* Error Message */}
          {error && (
            <div className="notification-error">
              <span>{error}</span>
              <button onClick={() => window.location.reload()}>Refresh</button>
            </div>
          )}

          {/* Notification Center */}
          <NotificationCenter
            userId={userId}
            maxHeight="70vh"
            isInline={true}
          />

          {/* Empty State */}
          {notifications.length === 0 && !error && (
            <div className="notification-empty">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor">
                <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"></path>
                <path d="M13.73 21a2 2 0 0 1-3.46 0"></path>
              </svg>
              <p>No notifications yet</p>
            </div>
          )}
        </div>
      )}

      {/* Backdrop */}
      {isOpen && (
        <div
          className="notification-backdrop"
          onClick={() => setIsOpen(false)}
        ></div>
      )}
    </div>
  );
};

export default NotificationBell;
