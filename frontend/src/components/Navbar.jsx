import React from 'react'
import useTradingStore from '../store/tradingStore'
import '../styles/navbar.css'

export default function Navbar() {
  const killSwitchTriggered = useTradingStore((s) => s.killSwitchTriggered)
  const botStatus = useTradingStore((s) => s.botStatus)
  const toggleKillSwitch = useTradingStore((s) => s.toggleKillSwitch)

  return (
    <nav className="navbar">
      <div className="navbar-left">
        <div className="logo">
          <span className="logo-icon">🤖</span>
          <span className="logo-text">AutoSaham</span>
        </div>
      </div>

      <div className="navbar-center">
        <span className={`status-badge ${botStatus}`}>
          <span className="status-dot"></span>
          {botStatus.charAt(0).toUpperCase() + botStatus.slice(1)}
        </span>
      </div> 

      <div className="navbar-right">
        {/* Kill Switch Button - MOST IMPORTANT ELEMENT */}
        <button
          className={`kill-switch ${killSwitchTriggered ? 'triggered' : 'active'}`}
          onClick={toggleKillSwitch}
          title="Emergency stop - halts all trading immediately"
        >
          <span className="kill-switch-icon">⏹️</span>
          <span className="kill-switch-text">
            {killSwitchTriggered ? 'STOPPED' : 'ACTIVE'}
          </span>
        </button>

        {/* User Menu Placeholder */}
        <div className="user-menu">
          <img
            src="https://api.dicebear.com/7.x/avataaars/svg?seed=AutoSaham"
            alt="User avatar"
            className="user-avatar"
          />
          <span className="user-name">Trader ID: ts_001</span>
        </div>
      </div>
    </nav>
  )
}
