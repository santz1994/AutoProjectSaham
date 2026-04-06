/**
 * Enhanced Navbar Component
 * Features: Notifications, Search, User Dropdown, Responsive Design
 */

import React, { useState, useRef, useEffect } from 'react';
import useTradingStore from '../store/tradingStore';
import Button from './Button';
import toast from '../store/toastStore';
import AuthService from '../utils/authService';
import '../styles/navbar-enhanced.css';

export default function NavbarEnhanced({ user = 'Trader', onLogout, onNavigate }) {
  const killSwitchTriggered = useTradingStore((s) => s.killSwitchTriggered);
  const botStatus = useTradingStore((s) => s.botStatus);
  const toggleKillSwitch = useTradingStore((s) => s.toggleKillSwitch);
  
  const [searchOpen, setSearchOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [notificationsOpen, setNotificationsOpen] = useState(false);
  const [userMenuOpen, setUserMenuOpen] = useState(false);
  const [notifications, setNotifications] = useState([
    { id: 1, type: 'success', message: 'Trade executed: BBCA bought at 8,250', time: '2 min ago', read: false },
    { id: 2, type: 'warning', message: 'Portfolio health score dropped to 72', time: '15 min ago', read: false },
    { id: 3, type: 'info', message: 'New AI signal: BMRI strong buy', time: '1 hour ago', read: true },
  ]);

  const searchRef = useRef(null);
  const notifRef = useRef(null);
  const userMenuRef = useRef(null);

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

  const handleKillSwitch = () => {
    toggleKillSwitch();
    if (!killSwitchTriggered) {
      toast.error('Emergency stop activated! All trading halted.', {
        duration: 5000,
        action: {
          label: 'Undo',
          onClick: () => toggleKillSwitch(),
        },
      });
    } else {
      toast.success('Trading resumed successfully', { duration: 3000 });
    }
  };

  const unreadCount = notifications.filter((n) => !n.read).length;

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
    setNotifications((prev) => prev.map((n) => ({ ...n, read: true })));
    toast.success('All notifications marked as read', { duration: 2000 });
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
                  placeholder="Search stocks, strategies, logs..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  aria-label="Search input"
                  autoFocus
                />
                <div className="search-suggestions">
                  <div className="suggestion-item">
                    <span className="suggestion-icon">📊</span>
                    <span>BBCA - Bank Central Asia</span>
                  </div>
                  <div className="suggestion-item">
                    <span className="suggestion-icon">📈</span>
                    <span>BMRI - Bank Mandiri</span>
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
                {notifications.map((notif) => (
                  <div
                    key={notif.id}
                    className={`notification-item ${notif.type} ${notif.read ? 'read' : 'unread'}`}
                    role="menuitem"
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
                onClick={() => toast.info('Profile page is coming soon')}
              >
                <span className="menu-icon">👤</span>
                <span>Profile</span>
              </div>
              <div
                className="menu-item"
                role="menuitem"
                tabIndex={0}
                onClick={() => {
                  if (onNavigate) {
                    onNavigate('settings');
                  }
                  setUserMenuOpen(false);
                }}
              >
                <span className="menu-icon">⚙️</span>
                <span>Settings</span>
              </div>
              <div
                className="menu-item"
                role="menuitem"
                tabIndex={0}
                onClick={() => toast.info('Theme switch is managed by responsive settings')}
              >
                <span className="menu-icon">🎨</span>
                <span>Theme</span>
              </div>
              <div className="menu-divider" role="separator"></div>
              <div
                className="menu-item"
                role="menuitem"
                tabIndex={0}
                onClick={() => toast.info('Help center is coming soon')}
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
