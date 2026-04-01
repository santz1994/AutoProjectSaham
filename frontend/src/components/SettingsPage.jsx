import React, { useState } from 'react'
import '../styles/settings.css'

export default function SettingsPage() {
  const [settings, setSettings] = useState({
    theme: 'dark',
    notifications: true,
    soundAlerts: false,
    emailReports: true,
    twoFactor: false,
    dailyReport: 'end-of-day',
    riskLevel: 'moderate',
    maxDrawdown: 15,
    apiKey: '****',
    brokerName: 'Indonesia Securities',
  })

  const [showApiKey, setShowApiKey] = useState(false)

  const handleToggle = (key) => {
    setSettings({ ...settings, [key]: !settings[key] })
  }

  const handleChange = (key, value) => {
    setSettings({ ...settings, [key]: value })
  }

  return (
    <div className="settings-page">
      <h1>⚙️ Settings & Configuration</h1>

      {/* Display Settings */}
      <div className="settings-section">
        <h2>🎨 Display Settings</h2>
        <div className="setting-item">
          <div className="setting-label">
            <span>Theme</span>
            <small>Choose your preferred color scheme</small>
          </div>
          <select
            value={settings.theme}
            onChange={(e) => handleChange('theme', e.target.value)}
            className="setting-input"
          >
            <option value="dark">Dark Mode</option>
            <option value="light">Light Mode</option>
            <option value="auto">Auto (System)</option>
          </select>
        </div>

        <div className="setting-item">
          <div className="setting-label">
            <span>Daily Report Time</span>
            <small>When should we send you daily reports?</small>
          </div>
          <select
            value={settings.dailyReport}
            onChange={(e) => handleChange('dailyReport', e.target.value)}
            className="setting-input"
          >
            <option value="morning">Morning (08:00 WIB)</option>
            <option value="noon">Noon (12:00 WIB)</option>
            <option value="end-of-day">End of Day (17:00 WIB)</option>
          </select>
        </div>
      </div>

      {/* Notification Settings */}
      <div className="settings-section">
        <h2>🔔 Notification Settings</h2>
        <div className="setting-item toggle">
          <div className="setting-label">
            <span>Enable Notifications</span>
            <small>Get browser notifications for important events</small>
          </div>
          <button
            className={`toggle-btn ${settings.notifications ? 'active' : ''}`}
            onClick={() => handleToggle('notifications')}
          >
            <span className="toggle-indicator"></span>
          </button>
        </div>

        <div className="setting-item toggle">
          <div className="setting-label">
            <span>Sound Alerts</span>
            <small>Play sound when trading signals arrive</small>
          </div>
          <button
            className={`toggle-btn ${settings.soundAlerts ? 'active' : ''}`}
            onClick={() => handleToggle('soundAlerts')}
          >
            <span className="toggle-indicator"></span>
          </button>
        </div>

        <div className="setting-item toggle">
          <div className="setting-label">
            <span>Email Reports</span>
            <small>Receive daily/weekly trading reports via email</small>
          </div>
          <button
            className={`toggle-btn ${settings.emailReports ? 'active' : ''}`}
            onClick={() => handleToggle('emailReports')}
          >
            <span className="toggle-indicator"></span>
          </button>
        </div>
      </div>

      {/* Risk Settings */}
      <div className="settings-section">
        <h2>⚠️ Risk Management</h2>
        <div className="setting-item">
          <div className="setting-label">
            <span>Risk Level</span>
            <small>Default risk profile for new strategies</small>
          </div>
          <select
            value={settings.riskLevel}
            onChange={(e) => handleChange('riskLevel', e.target.value)}
            className="setting-input"
          >
            <option value="conservative">Conservative (Low Risk)</option>
            <option value="moderate">Moderate (Balanced)</option>
            <option value="aggressive">Aggressive (High Risk)</option>
          </select>
        </div>

        <div className="setting-item">
          <div className="setting-label">
            <span>Max Drawdown Limit (%)</span>
            <small>Maximum portfolio decline before auto-stop</small>
          </div>
          <div className="slider-container">
            <input
              type="range"
              min="5"
              max="50"
              value={settings.maxDrawdown}
              onChange={(e) => handleChange('maxDrawdown', parseInt(e.target.value))}
              className="slider"
            />
            <span className="slider-value">{settings.maxDrawdown}%</span>
          </div>
        </div>
      </div>

      {/* Broker Settings */}
      <div className="settings-section">
        <h2>🔗 Broker Connection</h2>
        <div className="setting-item">
          <div className="setting-label">
            <span>Connected Broker</span>
            <small>Your trading account provider</small>
          </div>
          <div className="broker-info">
            <div className="broker-name">{settings.brokerName}</div>
            <button className="btn-secondary">Change Broker</button>
          </div>
        </div>

        <div className="setting-item">
          <div className="setting-label">
            <span>API Key</span>
            <small>For secure broker connection</small>
          </div>
          <div className="api-container">
            <input
              type={showApiKey ? 'text' : 'password'}
              value={settings.apiKey}
              readOnly
              className="setting-input api-key"
            />
            <button
              className="btn-icon"
              onClick={() => setShowApiKey(!showApiKey)}
              title="Toggle visibility"
            >
              {showApiKey ? '👁️' : '🔒'}
            </button>
            <button className="btn-secondary">Regenerate</button>
          </div>
        </div>
      </div>

      {/* Security Settings */}
      <div className="settings-section">
        <h2>🔐 Security</h2>
        <div className="setting-item toggle">
          <div className="setting-label">
            <span>Two-Factor Authentication</span>
            <small>Add extra security to your account</small>
          </div>
          <button
            className={`toggle-btn ${settings.twoFactor ? 'active' : ''}`}
            onClick={() => handleToggle('twoFactor')}
          >
            <span className="toggle-indicator"></span>
          </button>
        </div>
      </div>

      {/* Action Buttons */}
      <div className="settings-actions">
        <button className="btn-primary">Save Changes</button>
        <button className="btn-secondary">Reset to Defaults</button>
        <button className="btn-danger">Logout</button>
      </div>
    </div>
  )
}
