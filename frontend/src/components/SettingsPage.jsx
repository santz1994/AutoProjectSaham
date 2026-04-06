import React, { useEffect, useMemo, useState } from 'react'
import toast from '../store/toastStore'
import apiService from '../utils/apiService'
import AuthService from '../utils/authService'
import '../styles/settings.css'

const defaultSettings = {
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
}

const brokerOptions = [
  'Indonesia Securities',
  'Mandiri Sekuritas',
  'BCA Sekuritas',
  'Mirae Asset Sekuritas',
]

export default function SettingsPage({ onLogout }) {
  const [settings, setSettings] = useState(defaultSettings)
  const [initialSettings, setInitialSettings] = useState(defaultSettings)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)

  const [showApiKey, setShowApiKey] = useState(false)

  const hasChanges = useMemo(
    () => JSON.stringify(settings) !== JSON.stringify(initialSettings),
    [settings, initialSettings]
  )

  useEffect(() => {
    const loadSettings = async () => {
      setLoading(true)
      try {
        const remoteSettings = await apiService.getUserSettings()
        const merged = {
          ...defaultSettings,
          ...(remoteSettings || {}),
        }
        if (typeof window !== 'undefined') {
          localStorage.setItem('autosaham.theme', merged.theme || 'auto')
          window.dispatchEvent(new Event('autosaham:theme-changed'))
        }
        setSettings(merged)
        setInitialSettings(merged)
      } catch (error) {
        toast.warning('Failed to load settings from server. Using local defaults.')
        setSettings(defaultSettings)
        setInitialSettings(defaultSettings)
      } finally {
        setLoading(false)
      }
    }

    loadSettings()
  }, [])

  const handleToggle = (key) => {
    setSettings({ ...settings, [key]: !settings[key] })
  }

  const handleChange = (key, value) => {
    setSettings({ ...settings, [key]: value })
  }

  const handleSave = async () => {
    setSaving(true)
    try {
      const saved = await apiService.updateUserSettings(settings)
      const nextSettings = {
        ...settings,
        ...(saved || {}),
      }
      if (typeof window !== 'undefined') {
        localStorage.setItem('autosaham.theme', nextSettings.theme || 'auto')
        window.dispatchEvent(new Event('autosaham:theme-changed'))
      }
      setSettings(nextSettings)
      setInitialSettings(nextSettings)
      toast.success('Settings saved successfully')
    } catch (error) {
      toast.error(`Failed to save settings: ${error.message}`)
    } finally {
      setSaving(false)
    }
  }

  const handleResetToDefaults = () => {
    const resetSettings = { ...defaultSettings }
    setSettings(resetSettings)
    if (typeof window !== 'undefined') {
      localStorage.setItem('autosaham.theme', resetSettings.theme || 'auto')
      window.dispatchEvent(new Event('autosaham:theme-changed'))
    }
    toast.info('Settings reset to defaults. Click Save Changes to apply.')
  }

  const handleChangeBroker = () => {
    const currentIndex = brokerOptions.indexOf(settings.brokerName)
    const nextIndex = (currentIndex + 1) % brokerOptions.length
    const nextBroker = brokerOptions[nextIndex]

    setSettings((prev) => ({
      ...prev,
      brokerName: nextBroker,
    }))
    toast.info(`Broker switched to ${nextBroker}. Save changes to persist.`)
  }

  const handleRegenerateApiKey = () => {
    const token = Math.random().toString(36).slice(2, 10).toUpperCase()
    const refreshedKey = `AK-${token}-****`
    setSettings((prev) => ({
      ...prev,
      apiKey: refreshedKey,
    }))
    toast.success('New API key generated. Save changes to apply it.')
  }

  const handleLogout = async () => {
    try {
      const res = await AuthService.logout()
      if (!res.ok) {
        toast.error('Logout failed. Please try again.')
        return
      }
      toast.success('Logged out successfully')
      if (onLogout) {
        onLogout()
      }
    } catch (error) {
      toast.error('Logout failed. Please try again.')
    }
  }

  if (loading) {
    return (
      <div className="settings-page">
        <h1>⚙️ Settings & Configuration</h1>
        <div className="settings-section">
          <h2>Loading settings...</h2>
          <p style={{ color: '#94a3b8' }}>Please wait while we fetch your preferences.</p>
        </div>
      </div>
    )
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
            <button className="btn-secondary" onClick={handleChangeBroker} disabled={saving}>Change Broker</button>
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
            <button className="btn-secondary" onClick={handleRegenerateApiKey} disabled={saving}>Regenerate</button>
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
        <button className="btn-primary" onClick={handleSave} disabled={saving || !hasChanges}>
          {saving ? 'Saving...' : 'Save Changes'}
        </button>
        <button className="btn-secondary" onClick={handleResetToDefaults} disabled={saving}>
          Reset to Defaults
        </button>
        <button className="btn-danger" onClick={handleLogout} disabled={saving}>
          Logout
        </button>
      </div>
    </div>
  )
}
