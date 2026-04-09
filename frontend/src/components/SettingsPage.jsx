import React, { useEffect, useMemo, useRef, useState } from 'react'
import toast from '../store/toastStore'
import apiService from '../utils/apiService'
import AuthService from '../utils/authService'
import '../styles/settings.css'

const defaultSettings = {
    fullName: 'AutoSaham User',
    email: 'user@autosaham.local',
    phone: '',
  theme: 'auto',
    notifications: true,
    soundAlerts: false,
    emailReports: true,
    twoFactor: false,
    autoTrading: false,
    dailyReport: 'end-of-day',
    riskLevel: 'moderate',
    maxDrawdown: 15,
    brokerProvider: 'indonesia-securities',
    apiKey: '****',
    brokerName: 'Indonesia Securities',
    brokerAccountId: '',
    tradingMode: 'paper',
    maxOpenPositions: 5,
    preferredUniverse: ['BBCA.JK', 'USIM.JK', 'KLBF.JK', 'ASII.JK', 'UNVR.JK'],
    aiDefaultMarket: 'stocks',
    aiPredictionStyle: 'daily_trader',
    aiDefaultTimeframe: '15m',
    aiProjectionHorizon: 16,
    aiPredictionLockEnabled: true,
    aiMonitorRefreshSeconds: 20,
    aiManualStrategyProfile: 'auto',
}

const fallbackBrokerProviders = [
  { id: 'indonesia-securities', name: 'Indonesia Securities' },
  { id: 'ajaib', name: 'Ajaib' },
  { id: 'motiontrade', name: 'MotionTrade (MNC Sekuritas)' },
  { id: 'indopremier', name: 'Indo Premier' },
]
const AI_MARKET_OPTIONS = [
  { value: 'stocks', label: 'Saham (IDX)' },
  { value: 'forex', label: 'Forex' },
  { value: 'crypto', label: 'Blockchain/Crypto' },
  { value: 'index', label: 'Global Index' },
  { value: 'all', label: 'All Markets' },
]

const AI_PREDICTION_STYLE_OPTIONS = [
  { value: 'scalping', label: 'Scalping' },
  { value: 'daily_trader', label: 'Daily Trader' },
  { value: 'trader', label: 'Trader' },
]

const AI_TIMEFRAME_OPTIONS = ['1m', '5m', '15m', '30m', '1h', '4h', '1d', '1w', '1mo']
const AI_HORIZON_OPTIONS = [8, 12, 16, 24, 32]
const AI_PROFILE_MODE_OPTIONS = [
  { value: 'auto', label: 'Auto (Regime Router)' },
  { value: 'mean_reversion_swing', label: 'Manual: Mean Reversion Swing' },
  { value: 'momentum_breakout', label: 'Manual: Momentum Breakout' },
  { value: 'defensive_rotation', label: 'Manual: Defensive Rotation' },
]

const normalizeTwoFactorStatus = (payload = {}) => ({
  enabled: Boolean(payload?.enabled),
  required: Boolean(payload?.required),
  policyRequired: Boolean(payload?.policyRequired),
  configured: Boolean(payload?.configured),
  hasUserSecret: Boolean(payload?.hasUserSecret),
  enrollmentPending: Boolean(payload?.enrollmentPending),
  method: String(payload?.method || 'none'),
})

export default function SettingsPage({
  onLogout,
  currentThemePreference = 'auto',
  onThemePreferenceChange,
}) {
  const [settings, setSettings] = useState(defaultSettings)
  const [initialSettings, setInitialSettings] = useState(defaultSettings)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [availableBrokers, setAvailableBrokers] = useState(fallbackBrokerProviders)
  const [brokerFeatureFlags, setBrokerFeatureFlags] = useState({})
  const [brokerConnection, setBrokerConnection] = useState(null)
  const [connectingBroker, setConnectingBroker] = useState(false)
  const [syncingAiProfileMode, setSyncingAiProfileMode] = useState(false)
  const [twoFactorStatus, setTwoFactorStatus] = useState(normalizeTwoFactorStatus())
  const [twoFactorCode, setTwoFactorCode] = useState('')
  const [twoFactorSecret, setTwoFactorSecret] = useState('')
  const [twoFactorOtpAuthUri, setTwoFactorOtpAuthUri] = useState('')
  const [showTwoFactorSecret, setShowTwoFactorSecret] = useState(false)
  const [twoFactorBusy, setTwoFactorBusy] = useState(false)

  const [showApiKey, setShowApiKey] = useState(false)
  const profileSectionRef = useRef(null)

  const syncThemePreference = (nextTheme) => {
    const resolvedTheme = nextTheme || 'auto'

    if (typeof onThemePreferenceChange === 'function') {
      onThemePreferenceChange(resolvedTheme)
      return
    }

    if (typeof window !== 'undefined') {
      localStorage.setItem('autosaham.theme', resolvedTheme)
      window.dispatchEvent(new Event('autosaham:theme-changed'))
    }
  }

  const hasChanges = useMemo(
    () => JSON.stringify(settings) !== JSON.stringify(initialSettings),
    [settings, initialSettings]
  )

  useEffect(() => {
    const loadSettings = async () => {
      setLoading(true)
      try {
        const [remoteSettings, brokers, connection, featureFlags, twoFactorStatusRaw] = await Promise.all([
          apiService.getUserSettings().catch(() => null),
          apiService.getAvailableBrokers().catch(() => []),
          apiService.getBrokerConnection().catch(() => null),
          apiService.getBrokerFeatureFlags().catch(() => []),
          apiService.getTwoFactorStatus().catch(() => null),
        ])

        const twoFactorPayload = normalizeTwoFactorStatus(twoFactorStatusRaw)

        const merged = {
          ...defaultSettings,
          ...(remoteSettings || {}),
          theme: currentThemePreference || remoteSettings?.theme || defaultSettings.theme,
          twoFactor: twoFactorPayload.enabled,
        }

        if (connection?.connected) {
          merged.brokerName = connection.providerName || merged.brokerName
          merged.brokerAccountId = connection.accountId || merged.brokerAccountId
          merged.tradingMode = connection.tradingMode || merged.tradingMode
          merged.apiKey = connection.maskedApiKey || merged.apiKey
        }

        const safeBrokers = Array.isArray(brokers) && brokers.length > 0
          ? brokers
          : fallbackBrokerProviders
        const flagsMap = Array.isArray(featureFlags)
          ? featureFlags.reduce((acc, item) => {
              if (item?.provider) {
                acc[item.provider] = item
              }
              return acc
            }, {})
          : {}

        syncThemePreference(merged.theme)
        setSettings(merged)
        setInitialSettings(merged)
        setAvailableBrokers(safeBrokers)
        setBrokerFeatureFlags(flagsMap)
        setBrokerConnection(connection)
        setTwoFactorStatus(twoFactorPayload)
        if (twoFactorPayload.enabled) {
          setTwoFactorSecret('')
          setTwoFactorOtpAuthUri('')
          setTwoFactorCode('')
        }
      } catch (error) {
        const fallbackSettings = {
          ...defaultSettings,
          theme: currentThemePreference || defaultSettings.theme,
        }
        toast.warning('Failed to load settings from server. Using local defaults.')
        syncThemePreference(fallbackSettings.theme)
        setSettings(fallbackSettings)
        setInitialSettings(fallbackSettings)
        setAvailableBrokers(fallbackBrokerProviders)
        setBrokerFeatureFlags({})
        setBrokerConnection(null)
        setTwoFactorStatus(normalizeTwoFactorStatus())
      } finally {
        setLoading(false)
      }
    }

    loadSettings()
  }, [])

  useEffect(() => {
    if (!currentThemePreference) return
    setSettings((prev) => (
      prev.theme === currentThemePreference
        ? prev
        : {
            ...prev,
            theme: currentThemePreference,
          }
    ))
  }, [currentThemePreference])

  useEffect(() => {
    const openProfileSection = () => {
      if (!profileSectionRef.current) return

      profileSectionRef.current.scrollIntoView({ behavior: 'smooth', block: 'start' })
      const firstInput = profileSectionRef.current.querySelector('input')
      if (firstInput) {
        firstInput.focus()
      }
    }

    window.addEventListener('autosaham:open-profile', openProfileSection)
    return () => {
      window.removeEventListener('autosaham:open-profile', openProfileSection)
    }
  }, [])

  const handleToggle = (key) => {
    setSettings((prev) => ({ ...prev, [key]: !prev[key] }))
  }

  const handleChange = (key, value) => {
    setSettings((prev) => ({ ...prev, [key]: value }))
    if (key === 'theme') {
      syncThemePreference(value)
    }
  }

  const handleSave = async () => {
    setSaving(true)
    try {
      const { twoFactor, ...settingsPayload } = settings
      const saved = await apiService.updateUserSettings(settingsPayload)
      const nextSettings = {
        ...settings,
        ...(saved || {}),
        twoFactor: Boolean(twoFactorStatus.enabled),
      }
      syncThemePreference(nextSettings.theme)
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
    const resetSettings = {
      ...defaultSettings,
      twoFactor: Boolean(twoFactorStatus.enabled),
    }
    setSettings(resetSettings)
    syncThemePreference(resetSettings.theme)
    toast.info('Settings reset to defaults. Click Save Changes to apply.')
  }

  const handlePreferredUniverseChange = (value) => {
    const nextUniverse = value
      .split(',')
      .map((item) => item.trim().toUpperCase())
      .filter(Boolean)

    setSettings((prev) => ({
      ...prev,
      preferredUniverse: nextUniverse,
    }))
  }

  const handleConnectBroker = async () => {
    if (!settings.brokerAccountId?.trim()) {
      toast.error('Broker Account ID is required before connecting.')
      return
    }

    setConnectingBroker(true)
    try {
      const payload = {
        provider: settings.brokerProvider,
        accountId: settings.brokerAccountId,
        apiKey: settings.apiKey === '****' ? '' : settings.apiKey,
        tradingMode: settings.tradingMode,
      }

      const result = await apiService.connectBroker(payload)
      const nextConnection = result?.connection || null
      setBrokerConnection(nextConnection)

      setSettings((prev) => ({
        ...prev,
        brokerName: nextConnection?.providerName || prev.brokerName,
        brokerAccountId: nextConnection?.accountId || prev.brokerAccountId,
        apiKey: nextConnection?.maskedApiKey || prev.apiKey,
        tradingMode: nextConnection?.tradingMode || prev.tradingMode,
      }))

      if (nextConnection?.fallbackReason) {
        toast.warning(nextConnection.fallbackReason)
      }

      toast.success(`${nextConnection?.providerName || 'Broker'} connected in ${nextConnection?.tradingMode || 'paper'} mode.`)
    } catch (error) {
      toast.error(`Failed to connect broker: ${error.message}`)
    } finally {
      setConnectingBroker(false)
    }
  }

  const handleLiveFeatureFlagToggle = async (providerId, currentValue) => {
    try {
      const updated = await apiService.updateBrokerFeatureFlag(providerId, {
        liveEnabled: !currentValue,
      })

      setBrokerFeatureFlags((prev) => ({
        ...prev,
        [providerId]: updated,
      }))

      toast.success(`Live feature flag ${updated.liveEnabled ? 'enabled' : 'disabled'} for ${providerId}.`)
    } catch (error) {
      toast.error(`Failed to update feature flag: ${error.message}`)
    }
  }

  const handleDisconnectBroker = async () => {
    setConnectingBroker(true)
    try {
      const result = await apiService.disconnectBroker()
      setBrokerConnection(result?.connection || null)

      setSettings((prev) => ({
        ...prev,
        brokerAccountId: '',
        apiKey: '****',
        tradingMode: 'paper',
      }))

      toast.info('Broker connection disconnected. App remains in paper mode.')
    } catch (error) {
      toast.error(`Failed to disconnect broker: ${error.message}`)
    } finally {
      setConnectingBroker(false)
    }
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

  const handleResetAIProfileToAuto = async () => {
    setSyncingAiProfileMode(true)
    try {
      await apiService.resetAIProfileOverride()
      setSettings((prev) => ({
        ...prev,
        aiManualStrategyProfile: 'auto',
      }))
      setInitialSettings((prev) => ({
        ...prev,
        aiManualStrategyProfile: 'auto',
      }))
      toast.success('AI profile mode reset ke Auto (regime router).')
    } catch (error) {
      toast.error(`Failed to reset AI profile mode: ${error.message}`)
    } finally {
      setSyncingAiProfileMode(false)
    }
  }

  const refreshTwoFactorStatus = async () => {
    const nextStatusRaw = await apiService.getTwoFactorStatus()
    const nextStatus = normalizeTwoFactorStatus(nextStatusRaw)
    setTwoFactorStatus(nextStatus)
    setSettings((prev) => ({
      ...prev,
      twoFactor: nextStatus.enabled,
    }))
    setInitialSettings((prev) => ({
      ...prev,
      twoFactor: nextStatus.enabled,
    }))

    if (nextStatus.enabled) {
      setTwoFactorSecret('')
      setTwoFactorOtpAuthUri('')
      setTwoFactorCode('')
    }

    return nextStatus
  }

  const handleStartTwoFactorEnrollment = async () => {
    setTwoFactorBusy(true)
    try {
      const enrollment = await apiService.beginTwoFactorEnrollment()
      setTwoFactorSecret(String(enrollment?.secret || ''))
      setTwoFactorOtpAuthUri(String(enrollment?.otpauthUri || ''))
      setShowTwoFactorSecret(false)
      setTwoFactorCode('')
      await refreshTwoFactorStatus()
      toast.success('Two-factor setup initialized. Scan the secret and verify with a code.')
    } catch (error) {
      toast.error(`Failed to initialize two-factor setup: ${error.message}`)
    } finally {
      setTwoFactorBusy(false)
    }
  }

  const handleVerifyTwoFactorEnrollment = async () => {
    const code = String(twoFactorCode || '').trim()
    if (!code) {
      toast.error('Two-factor code is required to enable 2FA.')
      return
    }

    setTwoFactorBusy(true)
    try {
      await apiService.verifyTwoFactorEnrollment(code)
      await refreshTwoFactorStatus()
      toast.success('Two-factor authentication enabled.')
    } catch (error) {
      toast.error(`Failed to verify two-factor code: ${error.message}`)
    } finally {
      setTwoFactorBusy(false)
    }
  }

  const handleDisableTwoFactor = async () => {
    const code = String(twoFactorCode || '').trim()
    if (!code) {
      toast.error('Current two-factor code is required to disable 2FA.')
      return
    }

    setTwoFactorBusy(true)
    try {
      await apiService.disableTwoFactor(code)
      await refreshTwoFactorStatus()
      toast.info('Two-factor authentication disabled for this account.')
    } catch (error) {
      toast.error(`Failed to disable two-factor authentication: ${error.message}`)
    } finally {
      setTwoFactorBusy(false)
    }
  }

  const handleCopyTwoFactorSecret = async () => {
    const secret = String(twoFactorSecret || '').trim()
    if (!secret) {
      toast.error('No two-factor secret available to copy.')
      return
    }

    if (typeof navigator === 'undefined' || !navigator.clipboard?.writeText) {
      toast.error('Clipboard API is unavailable in this browser.')
      return
    }

    try {
      await navigator.clipboard.writeText(secret)
      toast.success('Two-factor secret copied to clipboard.')
    } catch (error) {
      toast.error('Unable to copy secret to clipboard.')
    }
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
          <p style={{ color: 'var(--text-secondary)' }}>Please wait while we fetch your preferences.</p>
        </div>
      </div>
    )
  }

  const selectedProviderMetadata = availableBrokers.find((item) => item.id === settings.brokerProvider)
  const selectedProviderFlag = brokerFeatureFlags[settings.brokerProvider] || {}
  const providerSupportsLive = Boolean(selectedProviderMetadata?.supportsLive)
  const providerLiveFeatureEnabled = Boolean(selectedProviderFlag?.liveEnabled)
  const providerIntegrationReady = selectedProviderFlag?.integrationReady ?? selectedProviderMetadata?.integrationReady
  const activeAiProfileMode = String(settings.aiManualStrategyProfile || 'auto').toLowerCase()
  const aiProfileModeLabel = activeAiProfileMode === 'auto'
    ? 'Automatic (Regime Router)'
    : `Manual (${activeAiProfileMode})`
  const twoFactorEnabled = Boolean(twoFactorStatus.enabled)
  const hasEnrollmentMaterial = Boolean(
    twoFactorSecret || twoFactorOtpAuthUri || twoFactorStatus.enrollmentPending
  )

  return (
    <div className="settings-page">
      <h1>⚙️ Settings & Configuration</h1>

      {/* Profile Settings */}
      <div className="settings-section" ref={profileSectionRef}>
        <h2>👤 Profile</h2>
        <div className="setting-item">
          <div className="setting-label">
            <span>Full Name</span>
            <small>Displayed in account and reporting screens</small>
          </div>
          <input
            type="text"
            value={settings.fullName}
            onChange={(e) => handleChange('fullName', e.target.value)}
            className="setting-input"
            placeholder="Your full name"
          />
        </div>
        <div className="setting-item">
          <div className="setting-label">
            <span>Email</span>
            <small>Primary account email for login and notifications</small>
          </div>
          <input
            type="email"
            value={settings.email}
            onChange={(e) => handleChange('email', e.target.value)}
            className="setting-input"
            placeholder="name@email.com"
          />
        </div>
        <div className="setting-item">
          <div className="setting-label">
            <span>Phone</span>
            <small>Optional for broker verification and urgent alerts</small>
          </div>
          <input
            type="tel"
            value={settings.phone}
            onChange={(e) => handleChange('phone', e.target.value)}
            className="setting-input"
            placeholder="+62..."
          />
        </div>
      </div>

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
            <span>Broker Provider</span>
            <small>Choose platform to link with this app (paper mode by default)</small>
          </div>
          <select
            value={settings.brokerProvider}
            onChange={(e) => {
              const nextProvider = availableBrokers.find((item) => item.id === e.target.value)
              handleChange('brokerProvider', e.target.value)
              if (nextProvider?.name) {
                handleChange('brokerName', nextProvider.name)
              }
            }}
            className="setting-input"
          >
            {availableBrokers.map((provider) => (
              <option key={provider.id} value={provider.id}>
                {provider.name}
              </option>
            ))}
          </select>
        </div>

        <div className="setting-item">
          <div className="setting-label">
            <span>Broker Account ID</span>
            <small>Your account identifier from broker dashboard</small>
          </div>
          <input
            type="text"
            value={settings.brokerAccountId}
            onChange={(e) => handleChange('brokerAccountId', e.target.value)}
            className="setting-input"
            placeholder="e.g. MT-00112233"
          />
        </div>

        <div className="setting-item">
          <div className="setting-label">
            <span>Trading Mode</span>
            <small>
              {providerLiveFeatureEnabled && providerIntegrationReady
                ? 'Live mode is enabled by feature flag for this provider.'
                : 'Live mode request will fallback to paper unless provider feature flag is enabled.'}
            </small>
          </div>
          <select
            value={settings.tradingMode}
            onChange={(e) => handleChange('tradingMode', e.target.value)}
            className="setting-input"
          >
            <option value="paper">Paper Trading (Recommended)</option>
            <option value="live" disabled={!providerSupportsLive}>
              {providerLiveFeatureEnabled && providerIntegrationReady
                ? 'Live Trading (Feature Enabled)'
                : 'Live Trading (Auto Fallback to Paper)'}
            </option>
          </select>
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
              onChange={(e) => handleChange('apiKey', e.target.value)}
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

        <div className="setting-item">
          <div className="setting-label">
            <span>Connection Status</span>
            <small>Current broker session in this app</small>
          </div>
          <div className="broker-status-container">
            <span className={`broker-status ${brokerConnection?.connected ? 'connected' : 'disconnected'}`}>
              {brokerConnection?.connected
                ? `Connected: ${brokerConnection.providerName || settings.brokerName}`
                : 'Not Connected'}
            </span>
            <div className="broker-actions">
              <button
                className="btn-primary"
                onClick={handleConnectBroker}
                disabled={connectingBroker || saving}
              >
                {connectingBroker ? 'Connecting...' : 'Connect Broker'}
              </button>
              <button
                className="btn-secondary"
                onClick={handleDisconnectBroker}
                disabled={connectingBroker || saving || !brokerConnection?.connected}
              >
                Disconnect
              </button>
            </div>
          </div>
        </div>

        <div className="setting-item">
          <div className="setting-label">
            <span>Broker Live Feature Flags (Beta)</span>
            <small>Enable live trading capability per provider (Ajaib/MotionTrade).</small>
          </div>
          <div className="broker-feature-flags">
            {availableBrokers
              .filter((provider) => provider.supportsLive)
              .map((provider) => {
                const providerFlag = brokerFeatureFlags[provider.id] || {
                  liveEnabled: false,
                  integrationReady: provider.integrationReady,
                }

                return (
                  <div className="broker-flag-row" key={provider.id}>
                    <div>
                      <strong>{provider.name}</strong>
                      <p>
                        Integration: {providerFlag.integrationReady ? 'Ready' : 'Not Ready'}
                      </p>
                    </div>
                    <button
                      className={`toggle-btn ${providerFlag.liveEnabled ? 'active' : ''}`}
                      onClick={() => handleLiveFeatureFlagToggle(provider.id, providerFlag.liveEnabled)}
                      disabled={saving || connectingBroker}
                      title={`Toggle live feature flag for ${provider.name}`}
                    >
                      <span className="toggle-indicator"></span>
                    </button>
                  </div>
                )
              })}
          </div>
        </div>
      </div>

      {/* AI Trading Universe */}
      <div className="settings-section">
        <h2>🧠 AI Universe & Execution</h2>
        <div className="setting-item">
          <div className="setting-label">
            <span>Preferred Universe</span>
            <small>Comma-separated ticker list used as AI screening universe</small>
          </div>
          <input
            type="text"
            value={(settings.preferredUniverse || []).join(', ')}
            onChange={(e) => handlePreferredUniverseChange(e.target.value)}
            className="setting-input"
            placeholder="BBCA.JK, TLKM.JK, ASII.JK"
          />
        </div>
        <div className="setting-item">
          <div className="setting-label">
            <span>Max Open Positions</span>
            <small>How many concurrent positions AI may hold</small>
          </div>
          <input
            type="number"
            min="1"
            max="20"
            value={settings.maxOpenPositions}
            onChange={(e) => handleChange('maxOpenPositions', parseInt(e.target.value || '1', 10))}
            className="setting-input"
          />
        </div>
        <div className="setting-item toggle">
          <div className="setting-label">
            <span>Enable Auto Trading</span>
            <small>Allow strategy execution manager to place orders automatically in selected mode</small>
          </div>
          <button
            className={`toggle-btn ${settings.autoTrading ? 'active' : ''}`}
            onClick={() => handleToggle('autoTrading')}
          >
            <span className="toggle-indicator"></span>
          </button>
        </div>
      </div>

      {/* AI Monitoring & Prediction Settings */}
      <div className="settings-section">
        <h2>🤖 AI Monitoring & Prediction</h2>

        <div className="setting-item">
          <div className="setting-label">
            <span>AI Strategy Profile Mode</span>
            <small>
              Auto mengikuti regime router. Manual akan mengunci profile sampai diubah/reset.
            </small>
          </div>
          <select
            value={settings.aiManualStrategyProfile || 'auto'}
            onChange={(e) => handleChange('aiManualStrategyProfile', e.target.value)}
            className="setting-input"
          >
            {AI_PROFILE_MODE_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </div>

        <div className="setting-item">
          <div className="setting-label">
            <span>Current AI Profile Source</span>
            <small>Mode aktif saat ini: {aiProfileModeLabel}</small>
          </div>
          <div className="setting-inline-actions">
            <span className={`settings-mode-pill ${activeAiProfileMode === 'auto' ? 'auto' : 'manual'}`}>
              {activeAiProfileMode === 'auto' ? 'AUTO' : 'MANUAL'}
            </span>
            <button
              className="btn-secondary"
              onClick={handleResetAIProfileToAuto}
              disabled={saving || syncingAiProfileMode || activeAiProfileMode === 'auto'}
            >
              {syncingAiProfileMode ? 'Resetting...' : 'Reset to Auto Now'}
            </button>
          </div>
        </div>

        <div className="setting-item">
          <div className="setting-label">
            <span>Default AI Market</span>
            <small>Market yang otomatis dibuka saat masuk ke AI Graph</small>
          </div>
          <select
            value={settings.aiDefaultMarket || 'stocks'}
            onChange={(e) => handleChange('aiDefaultMarket', e.target.value)}
            className="setting-input"
          >
            {AI_MARKET_OPTIONS.map((market) => (
              <option key={market.value} value={market.value}>
                {market.label}
              </option>
            ))}
          </select>
        </div>

        <div className="setting-item">
          <div className="setting-label">
            <span>Prediction Style</span>
            <small>Preset default saat AI Graph dibuka</small>
          </div>
          <select
            value={settings.aiPredictionStyle || 'daily_trader'}
            onChange={(e) => handleChange('aiPredictionStyle', e.target.value)}
            className="setting-input"
          >
            {AI_PREDICTION_STYLE_OPTIONS.map((style) => (
              <option key={style.value} value={style.value}>
                {style.label}
              </option>
            ))}
          </select>
        </div>

        <div className="setting-item">
          <div className="setting-label">
            <span>Default Timeframe</span>
            <small>Dipakai ketika preset style tidak mengoverride timeframe</small>
          </div>
          <select
            value={settings.aiDefaultTimeframe || '15m'}
            onChange={(e) => handleChange('aiDefaultTimeframe', e.target.value)}
            className="setting-input"
          >
            {AI_TIMEFRAME_OPTIONS.map((timeframe) => (
              <option key={timeframe} value={timeframe}>
                {timeframe}
              </option>
            ))}
          </select>
        </div>

        <div className="setting-item">
          <div className="setting-label">
            <span>Projection Horizon (steps)</span>
            <small>Panjang horizon prediksi default</small>
          </div>
          <select
            value={settings.aiProjectionHorizon || 16}
            onChange={(e) => handleChange('aiProjectionHorizon', parseInt(e.target.value, 10))}
            className="setting-input"
          >
            {AI_HORIZON_OPTIONS.map((step) => (
              <option key={step} value={step}>
                {step} steps
              </option>
            ))}
          </select>
        </div>

        <div className="setting-item toggle">
          <div className="setting-label">
            <span>Prediction Lock Enabled</span>
            <small>Lock update Current vs Target sesuai window timeframe</small>
          </div>
          <button
            className={`toggle-btn ${settings.aiPredictionLockEnabled ? 'active' : ''}`}
            onClick={() => handleToggle('aiPredictionLockEnabled')}
          >
            <span className="toggle-indicator"></span>
          </button>
        </div>

        <div className="setting-item">
          <div className="setting-label">
            <span>AI Monitor Refresh Interval (seconds)</span>
            <small>Auto-refresh interval untuk halaman AI Monitor (5-300 detik)</small>
          </div>
          <input
            type="number"
            min="5"
            max="300"
            value={settings.aiMonitorRefreshSeconds || 20}
            onChange={(e) => {
              const parsed = parseInt(e.target.value || '20', 10)
              const bounded = Number.isFinite(parsed)
                ? Math.max(5, Math.min(300, parsed))
                : 20
              handleChange('aiMonitorRefreshSeconds', bounded)
            }}
            className="setting-input"
          />
        </div>
      </div>

      {/* Funding and wallet note */}
      <div className="settings-section">
        <h2>💼 Funding & Wallet</h2>
        <p className="settings-note">
          This app currently tracks portfolio snapshot and risk settings. Cash deposit, withdrawal,
          and wallet transfer still happen on your broker app (Ajaib/MotionTrade/etc.) until live
          broker APIs are officially enabled.
        </p>
      </div>

      {/* Security Settings */}
      <div className="settings-section">
        <h2>🔐 Security</h2>
        <div className="setting-item">
          <div className="setting-label">
            <span>Two-Factor Authentication (TOTP)</span>
            <small>Use authenticator app code verification during login.</small>
          </div>
          <div className="setting-inline-actions">
            <span className={`settings-mode-pill ${twoFactorEnabled ? 'manual' : 'auto'}`}>
              {twoFactorEnabled ? 'ENABLED' : 'DISABLED'}
            </span>
            <button
              className="btn-secondary"
              onClick={handleStartTwoFactorEnrollment}
              disabled={twoFactorBusy || saving}
            >
              {twoFactorBusy
                ? 'Processing...'
                : (twoFactorEnabled ? 'Rotate Setup Secret' : 'Start Setup')}
            </button>
          </div>
        </div>

        {hasEnrollmentMaterial && !twoFactorEnabled && (
          <>
            <div className="setting-item">
              <div className="setting-label">
                <span>Provisioning Secret</span>
                <small>Scan manually in Google Authenticator/Authy/1Password.</small>
              </div>
              <div className="api-container">
                <input
                  type={showTwoFactorSecret ? 'text' : 'password'}
                  value={twoFactorSecret}
                  readOnly
                  className="setting-input api-key"
                />
                <button
                  className="btn-icon"
                  onClick={() => setShowTwoFactorSecret((prev) => !prev)}
                  title="Toggle visibility"
                >
                  {showTwoFactorSecret ? '🙈' : '👁️'}
                </button>
                <button className="btn-secondary" onClick={handleCopyTwoFactorSecret}>
                  Copy Secret
                </button>
              </div>
            </div>

            {twoFactorOtpAuthUri && (
              <div className="setting-item">
                <div className="setting-label">
                  <span>OTP Auth URI</span>
                  <small>Use this URI if your authenticator supports import links.</small>
                </div>
                <input
                  type="text"
                  value={twoFactorOtpAuthUri}
                  readOnly
                  className="setting-input"
                />
              </div>
            )}
          </>
        )}

        <div className="setting-item">
          <div className="setting-label">
            <span>{twoFactorEnabled ? 'Disable 2FA' : 'Enable 2FA'}</span>
            <small>
              {twoFactorEnabled
                ? 'Enter current authenticator code to disable two-factor login.'
                : 'Enter authenticator code to verify setup and enable two-factor login.'}
            </small>
          </div>
          <div className="setting-inline-actions">
            <input
              type="text"
              inputMode="numeric"
              pattern="[0-9]*"
              placeholder="6-digit code"
              value={twoFactorCode}
              onChange={(e) => setTwoFactorCode(e.target.value.replace(/\D/g, '').slice(0, 8))}
              className="setting-input two-factor-code"
              disabled={twoFactorBusy || saving}
            />
            {twoFactorEnabled ? (
              <button
                className="btn-danger"
                onClick={handleDisableTwoFactor}
                disabled={twoFactorBusy || saving || !String(twoFactorCode || '').trim()}
              >
                {twoFactorBusy ? 'Disabling...' : 'Disable 2FA'}
              </button>
            ) : (
              <button
                className="btn-primary"
                onClick={handleVerifyTwoFactorEnrollment}
                disabled={twoFactorBusy || saving || !String(twoFactorCode || '').trim()}
              >
                {twoFactorBusy ? 'Verifying...' : 'Verify & Enable'}
              </button>
            )}
          </div>
        </div>

        {twoFactorStatus.policyRequired && (
          <p className="settings-note two-factor-note">
            Two-factor login is currently enforced by server policy for your role.
          </p>
        )}
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
