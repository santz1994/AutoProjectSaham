import React, { useState } from 'react'
import '../styles/sidebar.css'

export default function Sidebar({ currentPage, onNavigate }) {
  const [isExpanded, setIsExpanded] = useState(true)

  const menuItems = [
    { id: 'dashboard', label: 'Dashboard', icon: '📊', desc: 'Portfolio & Status' },
    { id: 'market', label: 'Market Intelligence (Coming Soon)', icon: '📈', desc: 'Trends & Sentiment' },
    { id: 'strategies', label: 'Strategies (Coming Soon)', icon: '🎯', desc: 'Builder & Backtest' },
    { id: 'trades', label: 'Trade Logs (Coming Soon)', icon: '📝', desc: 'History & Analytics' },
    { id: 'settings', label: 'Settings (Coming Soon)', icon: '⚙️', desc: 'Configuration' },
  ]

  return (
    <aside className={`sidebar ${isExpanded ? 'expanded' : 'collapsed'}`}>
      <button
        className="sidebar-toggle"
        onClick={() => setIsExpanded(!isExpanded)}
        title={isExpanded ? 'Collapse' : 'Expand'}
      >
        {isExpanded ? '‹' : '›'}
      </button>

      <nav className="sidebar-nav">
        {menuItems.map((item) => (
          <button
            key={item.id}
            className={`nav-item ${currentPage === item.id ? 'active' : ''}`}
            onClick={() => onNavigate(item.id)}
            title={item.label}
          >
            <span className="nav-icon">{item.icon}</span>
            {isExpanded && (
              <div className="nav-label">
                <div className="nav-title">{item.label}</div>
                <div className="nav-desc">{item.desc}</div>
              </div>
            )}
          </button>
        ))}
      </nav>

      {isExpanded && (
        <div className="sidebar-footer">
          <div className="footer-info">
            <small>Jakarta WIB</small>
            <small className="timestamp">{new Date().toLocaleTimeString('id-ID')}</small>
          </div>
        </div>
      )}
    </aside>
  )
}
