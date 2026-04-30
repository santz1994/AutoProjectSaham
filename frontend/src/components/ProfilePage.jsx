import React, { useEffect, useMemo, useState } from 'react';
import toast from '../store/toastStore';
import apiService from '../utils/apiService';
import '../styles/profile.css';

const defaultProfileSettings = {
  fullName: 'AutoSaham User',
  email: 'user@autosaham.local',
  phone: '',
  riskLevel: 'moderate',
  dailyReport: 'end-of-day',
  theme: 'auto',
  twoFactor: false,
  brokerName: 'Not connected',
  brokerAccountId: '',
  tradingMode: 'paper',
};

export default function ProfilePage({ onNavigate }) {
  const [settings, setSettings] = useState(defaultProfileSettings);
  const [initialSettings, setInitialSettings] = useState(defaultProfileSettings);
  const [brokerConnection, setBrokerConnection] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  const hasChanges = useMemo(
    () => JSON.stringify(settings) !== JSON.stringify(initialSettings),
    [settings, initialSettings]
  );

  useEffect(() => {
    let active = true;

    const loadProfile = async () => {
      setLoading(true);
      try {
        const [userSettings, connection] = await Promise.all([
          apiService.getUserSettings(),
          apiService.getBrokerConnection().catch(() => null),
        ]);

        if (!active) return;

        const merged = {
          ...defaultProfileSettings,
          ...(userSettings || {}),
        };

        if (connection?.connected) {
          merged.brokerName = connection.providerName || merged.brokerName;
          merged.brokerAccountId = connection.accountId || merged.brokerAccountId;
          merged.tradingMode = connection.tradingMode || merged.tradingMode;
        }

        setSettings(merged);
        setInitialSettings(merged);
        setBrokerConnection(connection);
      } catch (error) {
        toast.error(`Failed to load profile: ${error.message}`);
      } finally {
        if (active) {
          setLoading(false);
        }
      }
    };

    loadProfile();

    return () => {
      active = false;
    };
  }, []);

  const handleChange = (key, value) => {
    setSettings((prev) => ({ ...prev, [key]: value }));
  };

  const handleToggle2FA = () => {
    setSettings((prev) => ({ ...prev, twoFactor: !prev.twoFactor }));
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      const saved = await apiService.updateUserSettings(settings);
      const merged = {
        ...settings,
        ...(saved || {}),
      };
      setSettings(merged);
      setInitialSettings(merged);
      toast.success('Profile updated successfully.');
    } catch (error) {
      toast.error(`Failed to save profile: ${error.message}`);
    } finally {
      setSaving(false);
    }
  };

  const handleReset = () => {
    setSettings(initialSettings);
    toast.info('Profile changes reset.');
  };

  if (loading) {
    return (
      <div className="profile-page">
        <h1>👤 Profile</h1>
        <div className="profile-card">
          <h2>Loading profile...</h2>
          <p>Please wait while we fetch your profile and account details.</p>
        </div>
      </div>
    );
  }

  const avatarSeed = encodeURIComponent(settings.fullName || settings.email || 'autosaham');

  return (
    <div className="profile-page">
      <div className="profile-header">
        <h1>👤 Profile</h1>
        <p>Manage account identity, security preferences, and connected broker summary.</p>
      </div>

      <div className="profile-layout">
        <section className="profile-card identity-card">
          <div className="identity-top">
            <img
              className="profile-avatar"
              src={`https://api.dicebear.com/7.x/avataaars/svg?seed=${avatarSeed}`}
              alt="Profile avatar"
            />
            <div>
              <h2>{settings.fullName || 'AutoSaham User'}</h2>
              <span className="profile-meta">Theme: {String(settings.theme || 'auto').toUpperCase()}</span>
            </div>
          </div>

          <div className="profile-grid">
            <label>
              <span>Full Name</span>
              <input
                type="text"
                value={settings.fullName || ''}
                onChange={(event) => handleChange('fullName', event.target.value)}
              />
            </label>

            <label>
              <span>Email</span>
              <input
                type="email"
                value={settings.email || ''}
                onChange={(event) => handleChange('email', event.target.value)}
              />
            </label>

            <label>
              <span>Phone</span>
              <input
                type="tel"
                value={settings.phone || ''}
                onChange={(event) => handleChange('phone', event.target.value)}
                placeholder="+62..."
              />
            </label>

            <label>
              <span>Risk Profile</span>
              <select
                value={settings.riskLevel || 'moderate'}
                onChange={(event) => handleChange('riskLevel', event.target.value)}
              >
                <option value="conservative">Conservative</option>
                <option value="moderate">Moderate</option>
                <option value="aggressive">Aggressive</option>
              </select>
            </label>

            <label>
              <span>Daily Report</span>
              <select
                value={settings.dailyReport || 'end-of-day'}
                onChange={(event) => handleChange('dailyReport', event.target.value)}
              >
                <option value="morning">Morning (08:00 WIB)</option>
                <option value="noon">Noon (12:00 WIB)</option>
                <option value="end-of-day">End of Day (17:00 WIB)</option>
              </select>
            </label>

            <label className="toggle-field">
              <span>Two-Factor Authentication</span>
              <button
                type="button"
                className={`toggle-btn ${settings.twoFactor ? 'active' : ''}`}
                onClick={handleToggle2FA}
              >
                <span className="toggle-indicator"></span>
              </button>
            </label>
          </div>
        </section>

        <aside className="profile-card account-card">
          <h2>Account & Broker</h2>

          <div className="account-row">
            <span>Status</span>
            <strong className={brokerConnection?.connected ? 'status-online' : 'status-offline'}>
              {brokerConnection?.connected ? 'Connected' : 'Paper Mode'}
            </strong>
          </div>
          <div className="account-row">
            <span>Broker</span>
            <strong>{settings.brokerName || 'Not connected'}</strong>
          </div>
          <div className="account-row">
            <span>Account ID</span>
            <strong>{settings.brokerAccountId || '-'}</strong>
          </div>
          <div className="account-row">
            <span>Execution Mode</span>
            <strong>{String(settings.tradingMode || 'paper').toUpperCase()}</strong>
          </div>

          <div className="profile-quick-actions">
            <button type="button" className="btn-secondary" onClick={() => onNavigate?.('settings')}>
              Open Settings
            </button>
            <button type="button" className="btn-secondary" onClick={() => onNavigate?.('ai-monitor')}>
              Open AI Monitor
            </button>
          </div>

          <p className="account-note">
            Wallet top-up and withdrawal still happen on your broker app. AutoSaham stores
            profile and execution preferences securely for orchestration.
          </p>
        </aside>
      </div>

      <div className="profile-actions">
        <button
          type="button"
          className="btn-primary"
          onClick={handleSave}
          disabled={!hasChanges || saving}
        >
          {saving ? 'Saving...' : 'Save Profile'}
        </button>
        <button
          type="button"
          className="btn-secondary"
          onClick={handleReset}
          disabled={saving || !hasChanges}
        >
          Reset Changes
        </button>
      </div>
    </div>
  );
}
