/**
 * Enhanced Sidebar Component
 * Features: Keyboard shortcuts, smooth animations, breadcrumbs
 */

import React, { useState, useEffect } from 'react';
import '../styles/sidebar-enhanced.css';

const menuItems = [
  { id: 'dashboard', label: 'Dashboard', icon: '📊', desc: 'Portfolio & Status', shortcut: '1' },
  { id: 'market', label: 'Market Intelligence', icon: '📈', desc: 'Trends & Sentiment', shortcut: '2' },
  { id: 'strategies', label: 'Strategies', icon: '🎯', desc: 'Builder & Backtest', shortcut: '3' },
  { id: 'trades', label: 'Trade Logs', icon: '📝', desc: 'History & Analytics', shortcut: '4' },
  { id: 'ai-monitor', label: 'AI Monitor', icon: '🧠', desc: 'Learning & Logs', shortcut: '5' },
  { id: 'profile', label: 'Profile', icon: '👤', desc: 'Identity & Account', shortcut: '6' },
  { id: 'settings', label: 'Settings', icon: '⚙️', desc: 'Configuration', shortcut: '7' },
];

export default function SidebarEnhanced({ currentPage, onNavigate }) {
  const [isExpanded, setIsExpanded] = useState(true);
  const [hoveredItem, setHoveredItem] = useState(null);
  const [showShortcuts, setShowShortcuts] = useState(false);

  // Keyboard shortcuts
  useEffect(() => {
    const handleKeyDown = (e) => {
      // Ctrl/Cmd + number for navigation
      if ((e.ctrlKey || e.metaKey) && /^[1-9]$/.test(e.key)) {
        e.preventDefault();
        const item = menuItems.find((i) => i.shortcut === e.key);
        if (item) {
          onNavigate(item.id);
        }
      }

      // Ctrl/Cmd + B to toggle sidebar
      if ((e.ctrlKey || e.metaKey) && e.key === 'b') {
        e.preventDefault();
        setIsExpanded((prev) => !prev);
      }

      // Ctrl/Cmd + / to show shortcuts
      if ((e.ctrlKey || e.metaKey) && e.key === '/') {
        e.preventDefault();
        setShowShortcuts((prev) => !prev);
      }
    };

    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [onNavigate]);

  const getCurrentTime = () => {
    return new Date().toLocaleTimeString('id-ID', {
      timeZone: 'Asia/Jakarta',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  const [currentTime, setCurrentTime] = useState(getCurrentTime());

  useEffect(() => {
    const timer = setInterval(() => {
      setCurrentTime(getCurrentTime());
    }, 1000);
    return () => clearInterval(timer);
  }, []);

  return (
    <>
      <aside
        className={`sidebar-enhanced ${isExpanded ? 'expanded' : 'collapsed'}`}
        role="navigation"
        aria-label="Main menu"
      >
        {/* Toggle Button */}
        <button
          className="sidebar-toggle"
          onClick={() => setIsExpanded(!isExpanded)}
          title={isExpanded ? 'Collapse sidebar (Ctrl+B)' : 'Expand sidebar (Ctrl+B)'}
          aria-label={isExpanded ? 'Collapse sidebar' : 'Expand sidebar'}
          aria-expanded={isExpanded}
        >
          <span className="toggle-icon">{isExpanded ? '‹' : '›'}</span>
        </button>

        {/* Navigation Menu */}
        <nav className="sidebar-nav" role="menu">
          {menuItems.map((item) => (
            <button
              key={item.id}
              className={`nav-item ${currentPage === item.id ? 'active' : ''}`}
              onClick={() => onNavigate(item.id)}
              onMouseEnter={() => setHoveredItem(item.id)}
              onMouseLeave={() => setHoveredItem(null)}
              title={`${item.label} (Ctrl+${item.shortcut})`}
              aria-label={`${item.label} - ${item.desc}`}
              aria-current={currentPage === item.id ? 'page' : undefined}
              role="menuitem"
            >
              <span className="nav-icon" aria-hidden="true">
                {item.icon}
              </span>

              {isExpanded && (
                <div className="nav-content">
                  <div className="nav-title">{item.label}</div>
                  <div className="nav-desc">{item.desc}</div>
                </div>
              )}

              {isExpanded && (
                <span className="nav-shortcut" aria-label={`Shortcut: Ctrl+${item.shortcut}`}>
                  ⌘{item.shortcut}
                </span>
              )}

              {/* Active indicator */}
              {currentPage === item.id && (
                <span className="active-indicator" aria-hidden="true" />
              )}

              {/* Hover tooltip when collapsed */}
              {!isExpanded && hoveredItem === item.id && (
                <div className="nav-tooltip" role="tooltip">
                  <div className="tooltip-title">{item.label}</div>
                  <div className="tooltip-desc">{item.desc}</div>
                  <div className="tooltip-shortcut">Ctrl+{item.shortcut}</div>
                </div>
              )}
            </button>
          ))}
        </nav>

        {/* Footer */}
        {isExpanded && (
          <div className="sidebar-footer">
            <div className="footer-info">
              <div className="footer-label">Jakarta WIB</div>
              <div className="footer-time">{currentTime}</div>
            </div>

            <button
              className="shortcuts-button"
              onClick={() => setShowShortcuts(true)}
              title="View keyboard shortcuts (Ctrl+/)"
              aria-label="View keyboard shortcuts"
            >
              <span className="shortcuts-icon">⌨️</span>
              <span>Shortcuts</span>
            </button>
          </div>
        )}
      </aside>

      {/* Keyboard Shortcuts Modal */}
      {showShortcuts && (
        <div
          className="shortcuts-modal-overlay"
          onClick={() => setShowShortcuts(false)}
          role="dialog"
          aria-modal="true"
          aria-labelledby="shortcuts-title"
        >
          <div className="shortcuts-modal" onClick={(e) => e.stopPropagation()}>
            <div className="shortcuts-header">
              <h2 id="shortcuts-title">Keyboard Shortcuts</h2>
              <button
                className="shortcuts-close"
                onClick={() => setShowShortcuts(false)}
                aria-label="Close shortcuts"
              >
                ×
              </button>
            </div>

            <div className="shortcuts-content">
              <div className="shortcuts-section">
                <h3>Navigation</h3>
                {menuItems.map((item) => (
                  <div key={item.id} className="shortcut-item">
                    <span className="shortcut-desc">{item.label}</span>
                    <kbd>Ctrl+{item.shortcut}</kbd>
                  </div>
                ))}
              </div>

              <div className="shortcuts-section">
                <h3>General</h3>
                <div className="shortcut-item">
                  <span className="shortcut-desc">Toggle Sidebar</span>
                  <kbd>Ctrl+B</kbd>
                </div>
                <div className="shortcut-item">
                  <span className="shortcut-desc">Search</span>
                  <kbd>Ctrl+K</kbd>
                </div>
                <div className="shortcut-item">
                  <span className="shortcut-desc">Keyboard Shortcuts</span>
                  <kbd>Ctrl+/</kbd>
                </div>
                <div className="shortcut-item">
                  <span className="shortcut-desc">Close Dialog</span>
                  <kbd>Esc</kbd>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
