/**
 * NotificationCenter - Main notification display component
 * Shows notification list with filtering, pagination, and actions
 * Jakarta timezone (WIB: UTC+7) aware
 */

import React, { useState, useCallback, useEffect } from 'react';
import useNotifications from '../hooks/useNotifications';
import './NotificationCenter.css';

const SEVERITY_COLORS = {
  info: '#0066cc',
  warning: '#ff9900',
  critical: '#cc0000',
  urgent: '#990000',
};

const SIGNAL_TYPE_LABELS = {
  buy_signal: '🟢 Buy Signal',
  sell_signal: '🔴 Sell Signal',
  stop_loss: '⛔ Stop Loss',
  take_profit: '💰 Take Profit',
  anomaly_detected: '⚠️ Anomaly',
  trend_change: '📈 Trend Change',
  volume_spike: '📊 Volume Spike',
  price_level: '📍 Price Level',
  portfolio_alert: '💼 Portfolio Alert',
  risk_warning: '🚨 Risk Warning',
};

export const NotificationCenter = ({
  userId,
  maxHeight = '500px',
  isInline = false,
}) => {
  const [filterSignalType, setFilterSignalType] = useState('');
  const [filterSeverity, setFilterSeverity] = useState('');
  const [filterRead, setFilterRead] = useState('unread'); // unread, read, all
  const [searchQuery, setSearchQuery] = useState('');
  const [sortBy, setSortBy] = useState('newest'); // newest, oldest, unread-first
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);

  const {
    notifications,
    isLoading,
    error,
    markAsRead,
    fetchNotifications,
    deleteNotification,
  } = useNotifications(userId);

  /**
   * Filter and sort notifications
   */
  const filteredNotifications = useCallback(() => {
    let filtered = [...notifications];

    // Filter by read status
    if (filterRead === 'unread') {
      filtered = filtered.filter((n) => !n.read);
    } else if (filterRead === 'read') {
      filtered = filtered.filter((n) => n.read);
    }

    // Filter by signal type
    if (filterSignalType) {
      filtered = filtered.filter((n) => n.signal_type === filterSignalType);
    }

    // Filter by severity
    if (filterSeverity) {
      filtered = filtered.filter((n) => n.severity === filterSeverity);
    }

    // Search in title and body
    if (searchQuery.trim()) {
      const query = searchQuery.toLowerCase();
      filtered = filtered.filter(
        (n) =>
          n.title?.toLowerCase().includes(query) ||
          n.body?.toLowerCase().includes(query) ||
          n.symbol?.toLowerCase().includes(query)
      );
    }

    // Sort
    if (sortBy === 'oldest') {
      filtered.sort(
        (a, b) => new Date(a.created_at) - new Date(b.created_at)
      );
    } else if (sortBy === 'unread-first') {
      filtered.sort((a, b) => {
        if (a.read === b.read) {
          return new Date(b.created_at) - new Date(a.created_at);
        }
        return a.read ? 1 : -1;
      });
    } else {
      // newest (default)
      filtered.sort(
        (a, b) => new Date(b.created_at) - new Date(a.created_at)
      );
    }

    return filtered;
  }, [notifications, filterSignalType, filterSeverity, filterRead, searchQuery, sortBy]);

  const filtered = filteredNotifications();
  const totalPages = Math.ceil(filtered.length / pageSize);
  const startIdx = (currentPage - 1) * pageSize;
  const displayedNotifications = filtered.slice(startIdx, startIdx + pageSize);

  /**
   * Format timestamp to Jakarta timezone
   */
  const formatTime = (timestamp) => {
    const date = new Date(timestamp);
    const jakartaTime = new Date(
      date.toLocaleString('en-US', { timeZone: 'Asia/Jakarta' })
    );
    
    const now = new Date();
    const diffMs = now - jakartaTime;
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);
    const diffDays = Math.floor(diffMs / 86400000);

    if (diffMins < 1) return 'just now';
    if (diffMins < 60) return `${diffMins}m ago`;
    if (diffHours < 24) return `${diffHours}h ago`;
    if (diffDays < 7) return `${diffDays}d ago`;

    return jakartaTime.toLocaleDateString('id-ID', {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  /**
   * Handle notification click
   */
  const handleNotificationClick = (notification) => {
    if (!notification.read) {
      markAsRead(notification.id);
    }
  };

  /**
   * Get signal type label with emoji
   */
  const getSignalTypeLabel = (signalType) => {
    return SIGNAL_TYPE_LABELS[signalType] || signalType;
  };

  return (
    <div className={`notification-center ${isInline ? 'inline' : 'standalone'}`}>
      {/* Toolbar */}
      <div className="notification-toolbar">
        {/* Search */}
        <div className="search-box">
          <input
            type="text"
            placeholder="Search notifications..."
            value={searchQuery}
            onChange={(e) => {
              setSearchQuery(e.target.value);
              setCurrentPage(1);
            }}
            className="search-input"
          />
          <svg
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            className="search-icon"
          >
            <circle cx="11" cy="11" r="8"></circle>
            <path d="m21 21-4.35-4.35"></path>
          </svg>
        </div>

        {/* Filters */}
        <div className="filter-group">
          <select
            value={filterRead}
            onChange={(e) => {
              setFilterRead(e.target.value);
              setCurrentPage(1);
            }}
            className="filter-select"
          >
            <option value="unread">Unread</option>
            <option value="read">Read</option>
            <option value="all">All</option>
          </select>

          <select
            value={filterSeverity}
            onChange={(e) => {
              setFilterSeverity(e.target.value);
              setCurrentPage(1);
            }}
            className="filter-select"
          >
            <option value="">All Severities</option>
            <option value="info">Info</option>
            <option value="warning">Warning</option>
            <option value="critical">Critical</option>
            <option value="urgent">Urgent</option>
          </select>

          <select
            value={sortBy}
            onChange={(e) => setSortBy(e.target.value)}
            className="filter-select"
          >
            <option value="newest">Newest First</option>
            <option value="oldest">Oldest First</option>
            <option value="unread-first">Unread First</option>
          </select>
        </div>
      </div>

      {/* Loading */}
      {isLoading && (
        <div className="notification-loading">
          <div className="spinner"></div>
          <p>Loading notifications...</p>
        </div>
      )}

      {/* Error */}
      {error && (
        <div className="notification-error-state">
          <svg viewBox="0 0 24 24" fill="currentColor">
            <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 18c-4.42 0-8-3.58-8-8s3.58-8 8-8 8 3.58 8 8-3.58 8-8 8zm3.5-9c.83 0 1.5-.67 1.5-1.5S16.33 8 15.5 8 14 8.67 14 9.5s.67 1.5 1.5 1.5zm-7 0c.83 0 1.5-.67 1.5-1.5S9.33 8 8.5 8 7 8.67 7 9.5 7.67 11 8.5 11zm3.5 6.5c2.33 0 4.31-1.46 5.11-3.5H6.89c.8 2.04 2.78 3.5 5.11 3.5z" />
          </svg>
          <p>{error}</p>
          <button onClick={() => fetchNotifications()}>Retry</button>
        </div>
      )}

      {/* Notification List */}
      <div className="notification-list" style={{ maxHeight }}>
        {displayedNotifications.length === 0 ? (
          <div className="notification-empty-state">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor">
              <circle cx="11" cy="11" r="8"></circle>
              <path d="m21 21-4.35-4.35"></path>
            </svg>
            <p>
              {filtered.length === 0
                ? 'No notifications found'
                : 'No notifications on this page'}
            </p>
          </div>
        ) : (
          displayedNotifications.map((notification) => (
            <div
              key={notification.id}
              className={`notification-item ${notification.read ? 'read' : 'unread'}`}
              onClick={() => handleNotificationClick(notification)}
            >
              {/* Status Indicator */}
              {!notification.read && <div className="unread-indicator"></div>}

              {/* Severity Dot */}
              <div
                className="severity-dot"
                style={{ backgroundColor: SEVERITY_COLORS[notification.severity] }}
                title={notification.severity}
              ></div>

              {/* Content */}
              <div className="notification-content">
                <div className="notification-header">
                  <h4 className="notification-title">
                    {getSignalTypeLabel(notification.signal_type)}
                  </h4>
                  <span className="notification-time">
                    {formatTime(notification.created_at)}
                  </span>
                </div>

                <p className="notification-body">{notification.title}</p>
                {notification.body && (
                  <p className="notification-description">{notification.body}</p>
                )}

                {/* Metadata */}
                <div className="notification-meta">
                  {notification.symbol && (
                    <span className="meta-item symbol">
                      📈 {notification.symbol}
                    </span>
                  )}
                  {notification.price && (
                    <span className="meta-item price">
                      💰 IDR {notification.price.toLocaleString('id-ID')}
                    </span>
                  )}
                  {notification.data?.change_percent && (
                    <span
                      className={`meta-item change ${
                        notification.data.change_percent >= 0
                          ? 'positive'
                          : 'negative'
                      }`}
                    >
                      {notification.data.change_percent >= 0 ? '📈' : '📉'}{' '}
                      {notification.data.change_percent.toFixed(2)}%
                    </span>
                  )}
                </div>

                {/* Channels Badge */}
                {notification.channels && (
                  <div className="notification-channels">
                    {notification.channels.map((channel) => (
                      <span key={channel} className="channel-badge">
                        {channel}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            </div>
          ))
        )}
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="notification-pagination">
          <button
            disabled={currentPage === 1}
            onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
            className="pagination-btn"
          >
            ← Previous
          </button>

          <div className="pagination-info">
            Page {currentPage} of {totalPages}
          </div>

          <button
            disabled={currentPage === totalPages}
            onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
            className="pagination-btn"
          >
            Next →
          </button>

          <select
            value={pageSize}
            onChange={(e) => {
              setPageSize(Number(e.target.value));
              setCurrentPage(1);
            }}
            className="page-size-select"
          >
            <option value="5">5 per page</option>
            <option value="10">10 per page</option>
            <option value="20">20 per page</option>
            <option value="50">50 per page</option>
          </select>
        </div>
      )}
    </div>
  );
};

export default NotificationCenter;
