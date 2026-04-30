/**
 * Enhanced Navbar Component
 * Features: Notifications, Search, User Dropdown, Responsive Design
 */

import React, { useState, useRef, useEffect } from 'react';
import useTradingStore from '../store/tradingStore';
import Button from './Button';
import toast from '../store/toastStore';
import AuthService from '../utils/authService';
import apiService from '../utils/apiService';
import { getWebSocketBase } from '../utils/authService';
import '../styles/navbar-enhanced.css';

function toNotificationType(severity) {
  const safeSeverity = String(severity || 'info').toLowerCase();
  if (safeSeverity === 'warning') {
    return 'warning';
  }
  if (safeSeverity === 'critical' || safeSeverity === 'urgent') {
    return 'danger';
  }
  return 'info';
}

function formatNotificationTime(isoTime) {
  if (!isoTime) {
    return 'just now';
  }

  const ts = new Date(isoTime).getTime();
  if (Number.isNaN(ts)) {
    return 'just now';
  }

  const diffSeconds = Math.max(0, Math.floor((Date.now() - ts) / 1000));
  if (diffSeconds < 60) {
    return 'just now';
  }
  if (diffSeconds < 3600) {
    return `${Math.floor(diffSeconds / 60)} min ago`;
  }
  if (diffSeconds < 86400) {
    return `${Math.floor(diffSeconds / 3600)} hour${Math.floor(diffSeconds / 3600) > 1 ? 's' : ''} ago`;
  }
  return `${Math.floor(diffSeconds / 86400)} day${Math.floor(diffSeconds / 86400) > 1 ? 's' : ''} ago`;
}

function mapHistoryNotification(item) {
  const createdAt = item?.created_at || item?.createdAt || new Date().toISOString();
  const title = String(item?.title || 'Notification');
  const body = String(item?.body || '').trim();
  const message = body ? `${title}: ${body}` : title;

  return {
    id: String(item?.id || `${Date.now()}-${Math.random()}`),
    type: toNotificationType(item?.severity),
    title,
    message,
    createdAt,
    time: formatNotificationTime(createdAt),
    read: Boolean(item?.read),
  };
}

function mapRealtimeNotification(payload) {
  const createdAt = payload?.created_at || payload?.createdAt || new Date().toISOString();
  const title = String(payload?.title || 'Notification');
  const body = String(payload?.body || '').trim();
  const message = body ? `${title}: ${body}` : title;

  return {
    id: String(payload?.id || `${Date.now()}-${Math.random()}`),
    type: toNotificationType(payload?.severity),
    title,
    message,
    createdAt,
    time: formatNotificationTime(createdAt),
    read: false,
  };
}

export default function NavbarEnhanced({
  user = 'Trader',
  onLogout,
  onNavigate,
  currentThemePreference = 'auto',
  onThemePreferenceChange,
}) {
  const killSwitchTriggered = useTradingStore((s) => s.killSwitchTriggered);
  const botStatus = useTradingStore((s) => s.botStatus);
  const setBotStatus = useTradingStore((s) => s.setBotStatus);
  const setKillSwitchState = useTradingStore((s) => s.setKillSwitchState);
  
  const [searchOpen, setSearchOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [notificationsOpen, setNotificationsOpen] = useState(false);
  const [userMenuOpen, setUserMenuOpen] = useState(false);
  const [notifications, setNotifications] = useState([]);
  const [unreadCountHint, setUnreadCountHint] = useState(0);
  const [notificationsLoading, setNotificationsLoading] = useState(false);
  const [notificationsError, setNotificationsError] = useState('');
  const [killSwitchLoading, setKillSwitchLoading] = useState(false);

  const searchRef = useRef(null);
  const notifRef = useRef(null);
  const userMenuRef = useRef(null);
  const notifSocketRef = useRef(null);
  const notifSocketReconnectRef = useRef(null);
  const notifPingRef = useRef(null);
  const shouldReconnectRef = useRef(true);
  const notificationUserId = String(user || '').trim();

  const refreshNotificationTimes = () => {
    setNotifications((prev) => prev.map((item) => ({
      ...item,
      time: formatNotificationTime(item.createdAt),
    })));
  };

  const loadNotifications = async () => {
    if (!notificationUserId) {
      setNotifications([]);
      return;
    }

    setNotificationsLoading(true);
    setNotificationsError('');

    try {
      const [historyRes, unreadRes] = await Promise.all([
        apiService.getNotifications(notificationUserId, 40, 0),
        apiService.getUnreadNotificationsCount(notificationUserId),
      ]);

      const list = Array.isArray(historyRes?.notifications)
        ? historyRes.notifications.map(mapHistoryNotification)
        : [];

      setUnreadCountHint(Math.max(0, Number(unreadRes?.unread_count || 0)));
      setNotifications(list);
    } catch (error) {
      setNotificationsError(error?.message || 'Failed to load notifications');
    } finally {
      setNotificationsLoading(false);
    }
  };

  const clearNotificationSocket = () => {
    if (notifPingRef.current) {
      clearInterval(notifPingRef.current);
      notifPingRef.current = null;
    }

    if (notifSocketReconnectRef.current) {
      clearTimeout(notifSocketReconnectRef.current);
      notifSocketReconnectRef.current = null;
    }

    if (notifSocketRef.current) {
      try {
        notifSocketRef.current.close();
      } catch (error) {
        // Ignore close errors during teardown.
      }
      notifSocketRef.current = null;
    }
  };

  const connectNotificationSocket = () => {
    if (!notificationUserId) {
      return;
    }

    clearNotificationSocket();

    try {
      const wsBase = getWebSocketBase();
      const safeUser = encodeURIComponent(notificationUserId);
      const socket = new WebSocket(`${wsBase}/api/notifications/ws/${safeUser}`);
      notifSocketRef.current = socket;

      socket.onopen = () => {
        notifPingRef.current = setInterval(() => {
          if (socket.readyState === WebSocket.OPEN) {
            socket.send(JSON.stringify({ type: 'ping' }));
          }
        }, 25000);
      };

      socket.onmessage = (event) => {
        try {
          const payload = JSON.parse(event.data || '{}');

          if (payload.type === 'notification') {
            const incoming = mapRealtimeNotification(payload);
            setNotifications((prev) => {
              const withoutDuplicate = prev.filter((item) => item.id !== incoming.id);
              return [incoming, ...withoutDuplicate].slice(0, 80);
            });
            setUnreadCountHint((prev) => prev + 1);

            if (payload.severity === 'critical' || payload.severity === 'urgent') {
              toast.error(incoming.message, { duration: 5000 });
            }
          }

          if (payload.type === 'read_confirmed' && payload.notification_id) {
            setNotifications((prev) => prev.map((item) => (
              item.id === String(payload.notification_id)
                ? { ...item, read: true }
                : item
            )));
            setUnreadCountHint((prev) => Math.max(0, prev - 1));
          }
        } catch (error) {
          // Ignore malformed websocket payloads.
        }
      };

      socket.onclose = (event) => {
        const closeCode = Number(event?.code || 0);
        if (closeCode === 4401 || closeCode === 4403) {
          shouldReconnectRef.current = false;
          setNotificationsError('Notification socket unauthorized. Please login again.');
          return;
        }

        if (!shouldReconnectRef.current) {
          return;
        }

        notifSocketReconnectRef.current = setTimeout(() => {
          connectNotificationSocket();
        }, 2500);
      };
    } catch (error) {
      // Connection setup failure should not break the navbar.
    }
  };

  const syncKillSwitchState = async () => {
    try {
      const state = await apiService.getKillSwitchState();
      const active = Boolean(state?.killSwitchActive);
      const stamp = state?.activatedAt || state?.updatedAt || new Date().toISOString();
      setKillSwitchState(active, stamp);
      if (active) {
        setBotStatus('stopped');
      }
    } catch (error) {
      // Keep existing local state when backend state cannot be fetched.
    }
  };

  // Close dropdowns when clicking outside
  useEffect(() => {
    const handleClickOutside = (event) => {
      if (searchRef.current && !searchRef.current.contains(event.target)) {
        setSearchOpen(false);
      }
      if (notifRef.current && !notifRef.current.contains(event.target)) {
        setNotificationsOpen(false);
      }
      if (userMenuRef.current && !userMenuRef.current.contains(event.target)) {
        setUserMenuOpen(false);
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  // Keyboard shortcut for search (Ctrl+K)
  useEffect(() => {
    const handleKeyDown = (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
        e.preventDefault();
        setSearchOpen(true);
        setTimeout(() => searchRef.current?.querySelector('input')?.focus(), 100);
      }
      if (e.key === 'Escape') {
        setSearchOpen(false);
        setNotificationsOpen(false);
        setUserMenuOpen(false);
      }
    };

    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, []);

  useEffect(() => {
    syncKillSwitchState();
  }, []);

  const resolveChallengeCodeFromError = (error, actionLabel) => {
    const message = String(error?.message || '').toLowerCase();
    if (!message.includes('2fa')) {
      return null;
    }

    const promptMessage = `2FA code required to ${actionLabel} kill switch. Enter challenge code:`;
    const code = window.prompt(promptMessage, '');
    if (code === null) {
      return null;
    }

    const trimmed = String(code).trim();
    return trimmed || null;
  };

  const handleKillSwitch = async () => {
    if (killSwitchLoading) {
      return;
    }

    setKillSwitchLoading(true);
    try {
      if (!killSwitchTriggered) {
        let result;
        try {
          result = await apiService.activateKillSwitch(
            'Emergency stop activated from navbar',
            'ui-navbar',
          );
        } catch (firstError) {
          const challengeCode = resolveChallengeCodeFromError(firstError, 'activate');
          if (!challengeCode) {
            throw firstError;
          }
          result = await apiService.activateKillSwitch(
            'Emergency stop activated from navbar',
            'ui-navbar',
            { challengeCode },
          );
        }

        setKillSwitchState(true, result?.killSwitch?.activatedAt || result?.killSwitch?.updatedAt || null);
        setBotStatus('stopped');
        toast.error('Emergency stop activated! All trading halted.', { duration: 5000 });
      } else {
        let result;
        try {
          result = await apiService.deactivateKillSwitch(
            'Trading resumed from navbar',
            'ui-navbar',
          );
        } catch (firstError) {
          const challengeCode = resolveChallengeCodeFromError(firstError, 'deactivate');
          if (!challengeCode) {
            throw firstError;
          }
          result = await apiService.deactivateKillSwitch(
            'Trading resumed from navbar',
            'ui-navbar',
            { challengeCode },
          );
        }

        setKillSwitchState(false, result?.killSwitch?.updatedAt || null);
        setBotStatus('idle');
        toast.success('Trading resumed successfully', { duration: 3000 });
      }
    } catch (error) {
      toast.error(error?.message || 'Failed to update kill switch state');
    } finally {
      setKillSwitchLoading(false);
    }
  };

  useEffect(() => {
    if (!notificationUserId) {
      return undefined;
    }

    shouldReconnectRef.current = true;
    loadNotifications();
    connectNotificationSocket();

    const refreshTimer = setInterval(() => {
      refreshNotificationTimes();
    }, 60000);

    const syncTimer = setInterval(() => {
      loadNotifications();
    }, 90000);

    return () => {
      shouldReconnectRef.current = false;
      clearInterval(refreshTimer);
      clearInterval(syncTimer);
      clearNotificationSocket();
    };
  }, [notificationUserId]);

  const unreadCount = Math.max(
    notifications.filter((n) => !n.read).length,
    unreadCountHint,
  );

  const handleSearch = (e) => {
    e.preventDefault();
    if (searchQuery.trim()) {
      toast.info(`Searching for: ${searchQuery}`, { duration: 2000 });
      // Implement actual search logic here
      setSearchQuery('');
      setSearchOpen(false);
    }
  };

  const markAllAsRead = () => {
    if (!notificationUserId) {
      return;
    }

    apiService
      .markAllNotificationsRead(notificationUserId)
      .then((result) => {
        const affected = Number(result?.count || 0);
        if (affected > 0) {
          setNotifications((prev) => prev.map((n) => ({ ...n, read: true })));
          setUnreadCountHint(0);
          toast.success('All notifications marked as read', { duration: 2000 });
        }
      })
      .catch((error) => {
        toast.error(error?.message || 'Failed to mark all notifications as read');
      });
  };

  const markNotificationAsRead = async (notification) => {
    if (!notification || notification.read || !notificationUserId) {
      return;
    }

    try {
      await apiService.markNotificationRead(notification.id, notificationUserId);
      setNotifications((prev) => prev.map((item) => (
        item.id === notification.id
          ? { ...item, read: true }
          : item
      )));
      setUnreadCountHint((prev) => Math.max(0, prev - 1));
    } catch (error) {
      toast.error(error?.message || 'Failed to mark notification as read');
    }
  };

  const handleLogout = async () => {
    try {
      const res = await AuthService.logout();
      if (!res.ok) {
        toast.error('Logout failed. Please try again.');
        return;
      }
      toast.success('Logged out successfully');
      if (onLogout) {
        onLogout();
      }
    } catch (error) {
      toast.error('Logout failed. Please try again.');
    }
  };

  const openSettingsFromMenu = (message) => {
    if (typeof onNavigate === 'function') {
      onNavigate('settings');
    }
    setUserMenuOpen(false);
    if (message) {
      toast.info(message);
    }
  };

  const openProfileFromMenu = () => {
    if (typeof onNavigate === 'function') {
      onNavigate('profile');
    }

    setUserMenuOpen(false);
  };

  const handleThemeMenuClick = () => {
    const themeOrder = ['dark', 'light', 'auto'];
    const themeLabels = {
      dark: 'Dark Mode',
      light: 'Light Mode',
      auto: 'Auto (System)',
    };
    const currentIndex = themeOrder.indexOf(currentThemePreference);
    const nextTheme = themeOrder[(currentIndex + 1 + themeOrder.length) % themeOrder.length];

    if (typeof onThemePreferenceChange === 'function') {
      onThemePreferenceChange(nextTheme);
      toast.success(`Theme updated to ${themeLabels[nextTheme]}`, { duration: 2000 });
    } else {
      toast.info('Theme options are available in Settings');
    }

    setUserMenuOpen(false);
  };

  return (
    <nav className="navbar-enhanced" role="navigation" aria-label="Main navigation">
      {/* Left Section */}
      <div className="navbar-left">
        <div className="logo" role="img" aria-label="AutoSaham Logo">
          <span className="logo-icon">🤖</span>
          <span className="logo-text">AutoSaham</span>
        </div>

        {/* Search */}
        <div className="search-container" ref={searchRef}>
          <button
            className="search-trigger"
            onClick={() => setSearchOpen(!searchOpen)}
            aria-label="Open search"
            aria-expanded={searchOpen}
            aria-controls="search-dropdown"
          >
            <span className="search-icon">🔍</span>
            <span className="search-hint">Search (Ctrl+K)</span>
          </button>

          {searchOpen && (
            <div className="search-dropdown" id="search-dropdown" role="search">
              <form onSubmit={handleSearch}>
                <input
                  type="text"
                  className="search-input"
                  placeholder="Search forex, crypto, strategies, logs..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  aria-label="Search input"
                  autoFocus
                />
                <div className="search-suggestions">
                  <div className="suggestion-item">
                    <span className="suggestion-icon">📊</span>
                    <span>EURUSD - Euro / US Dollar</span>
                  </div>
                  <div className="suggestion-item">
                    <span className="suggestion-icon">📈</span>
                    <span>BTC-USD - Bitcoin</span>
                  </div>
                  <div className="suggestion-item">
                    <span className="suggestion-icon">🎯</span>
                    <span>Momentum Strategy</span>
                  </div>
                </div>
              </form>
            </div>
          )}
        </div>
      </div>

      {/* Center Section - Bot Status */}
      <div className="navbar-center">
        <span className={`status-badge ${botStatus}`} role="status" aria-live="polite">
          <span className="status-dot" aria-hidden="true"></span>
          {botStatus.charAt(0).toUpperCase() + botStatus.slice(1)}
        </span>
      </div>

      {/* Right Section */}
      <div className="navbar-right">
        {/* Notifications */}
        <div className="notifications-container" ref={notifRef}>
          <button
            className="icon-button"
            onClick={() => setNotificationsOpen(!notificationsOpen)}
            aria-label={`Notifications ${unreadCount > 0 ? `(${unreadCount} unread)` : ''}`}
            aria-expanded={notificationsOpen}
            aria-controls="notifications-dropdown"
          >
            <span className="icon">🔔</span>
            {unreadCount > 0 && (
              <span className="notification-badge" aria-label={`${unreadCount} unread`}>
                {unreadCount}
              </span>
            )}
          </button>

          {notificationsOpen && (
            <div className="notifications-dropdown" id="notifications-dropdown" role="menu">
              <div className="dropdown-header">
                <h3>Notifications</h3>
                <button
                  className="mark-read-btn"
                  onClick={markAllAsRead}
                  disabled={unreadCount === 0}
                >
                  Mark all as read
                </button>
              </div>
              <div className="notifications-list">
                {notificationsLoading && (
                  <div className="notification-item read" role="menuitem">
                    <div className="notif-content">
                      <p className="notif-message">Loading notifications...</p>
                    </div>
                  </div>
                )}
                {notificationsError && !notificationsLoading && (
                  <div className="notification-item read" role="menuitem">
                    <div className="notif-content">
                      <p className="notif-message">{notificationsError}</p>
                    </div>
                  </div>
                )}
                {!notificationsLoading && !notificationsError && notifications.length === 0 && (
                  <div className="notification-item read" role="menuitem">
                    <div className="notif-content">
                      <p className="notif-message">No notifications yet</p>
                    </div>
                  </div>
                )}
                {!notificationsLoading && !notificationsError && notifications.map((notif) => (
                  <div
                    key={notif.id}
                    className={`notification-item ${notif.type} ${notif.read ? 'read' : 'unread'}`}
                    role="menuitem"
                    onClick={() => markNotificationAsRead(notif)}
                  >
                    <div className="notif-content">
                      <p className="notif-message">{notif.message}</p>
                      <span className="notif-time">{notif.time}</span>
                    </div>
                    {!notif.read && <span className="unread-dot" aria-label="Unread"></span>}
                  </div>
                ))}
              </div>
              <div className="dropdown-footer">
                <button className="view-all-btn" onClick={() => setNotificationsOpen(false)}>
                  View all notifications
                </button>
              </div>
            </div>
          )}
        </div>

        {/* Kill Switch */}
        <Button
          variant={killSwitchTriggered ? 'danger' : 'success'}
          size="md"
          onClick={handleKillSwitch}
          loading={killSwitchLoading}
          icon={<span>{killSwitchTriggered ? '⏹️' : '▶️'}</span>}
          title={killSwitchTriggered ? 'Resume Trading' : 'Emergency Stop'}
          ariaLabel={killSwitchTriggered ? 'Resume trading' : 'Emergency stop - halts all trading'}
          className="kill-switch-btn"
        >
          {killSwitchTriggered ? 'STOPPED' : 'ACTIVE'}
        </Button>

        {/* User Menu */}
        <div className="user-menu-container" ref={userMenuRef}>
          <button
            className="user-menu-trigger"
            onClick={() => setUserMenuOpen(!userMenuOpen)}
            aria-label="User menu"
            aria-expanded={userMenuOpen}
            aria-controls="user-menu-dropdown"
            aria-haspopup="true"
          >
            <img
              src="https://api.dicebear.com/7.x/avataaars/svg?seed=AutoSaham"
              alt=""
              className="user-avatar"
              aria-hidden="true"
            />
            <span className="user-name">{user}</span>
            <span className="dropdown-arrow" aria-hidden="true">
              {userMenuOpen ? '▲' : '▼'}
            </span>
          </button>

          {userMenuOpen && (
            <div className="user-menu-dropdown" id="user-menu-dropdown" role="menu">
              <div
                className="menu-item"
                role="menuitem"
                tabIndex={0}
                onClick={openProfileFromMenu}
              >
                <span className="menu-icon">👤</span>
                <span>Profile</span>
              </div>
              <div
                className="menu-item"
                role="menuitem"
                tabIndex={0}
                onClick={() => {
                  openSettingsFromMenu();
                }}
              >
                <span className="menu-icon">⚙️</span>
                <span>Settings</span>
              </div>
              <div
                className="menu-item"
                role="menuitem"
                tabIndex={0}
                onClick={handleThemeMenuClick}
              >
                <span className="menu-icon">🎨</span>
                <span>Theme</span>
              </div>
              <div
                className="menu-item"
                role="menuitem"
                tabIndex={0}
                onClick={() => {
                  if (typeof onNavigate === 'function') {
                    onNavigate('ai-graph');
                  }
                  setUserMenuOpen(false);
                }}
              >
                <span className="menu-icon">🔮</span>
                <span>AI Graph</span>
              </div>
              <div
                className="menu-item"
                role="menuitem"
                tabIndex={0}
                onClick={() => {
                  if (typeof onNavigate === 'function') {
                    onNavigate('ai-monitor');
                  }
                  setUserMenuOpen(false);
                }}
              >
                <span className="menu-icon">🧠</span>
                <span>AI Monitor</span>
              </div>
              <div className="menu-divider" role="separator"></div>
              <div
                className="menu-item"
                role="menuitem"
                tabIndex={0}
                onClick={() => openSettingsFromMenu('Help and support shortcuts are available in Settings.')}
              >
                <span className="menu-icon">❓</span>
                <span>Help & Support</span>
              </div>
              <div className="menu-item danger" role="menuitem" tabIndex={0} onClick={handleLogout}>
                <span className="menu-icon">🚪</span>
                <span>Logout</span>
              </div>
            </div>
          )}
        </div>
      </div>
    </nav>
  );
}
