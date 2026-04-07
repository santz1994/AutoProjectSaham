import React, { useState, useEffect } from 'react'
import Button from './Button'
import toast from '../store/toastStore'
import { CardSkeleton } from './LoadingSkeletons'
import apiService from '../utils/apiService'
import '../styles/strategies.css'

function isEndpointUnavailable(error) {
  const message = String(error?.message || '').toLowerCase()
  return message.includes('404') || message.includes('not found')
}

const AI_PROFILE_OPTIONS = [
  { value: 'auto', label: 'Auto (Regime Router)' },
  { value: 'mean_reversion_swing', label: 'Manual: Mean Reversion Swing' },
  { value: 'momentum_breakout', label: 'Manual: Momentum Breakout' },
  { value: 'defensive_rotation', label: 'Manual: Defensive Rotation' },
]

const AI_PROFILE_LABELS = {
  auto: 'Auto (Regime Router)',
  mean_reversion_swing: 'Mean Reversion Swing',
  momentum_breakout: 'Momentum Breakout',
  defensive_rotation: 'Defensive Rotation',
}

export default function StrategiesPage() {
  const [selectedStrategy, setSelectedStrategy] = useState(null)
  const [strategies, setStrategies] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [deployingId, setDeployingId] = useState(null)
  const [backtestingId, setBacktestingId] = useState(null)
  const [aiProfileModeValue, setAiProfileModeValue] = useState('auto')
  const [regimeSnapshot, setRegimeSnapshot] = useState(null)
  const [syncingProfileMode, setSyncingProfileMode] = useState(false)

  const loadStrategies = async () => {
    setLoading(true)
    setError(null)
    try {
      const [data, userSettings, regime] = await Promise.all([
        apiService.getStrategies(),
        apiService.getUserSettings().catch(() => null),
        apiService.getAIRegimeStatus().catch(() => null),
      ])
      setStrategies(data)
      setAiProfileModeValue(String(userSettings?.aiManualStrategyProfile || 'auto').toLowerCase())
      setRegimeSnapshot(regime || null)
    } catch (err) {
      const errorMsg = err.message || 'Failed to load strategies'
      setError(errorMsg)
      toast.error(errorMsg)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadStrategies()
  }, [])

  const handleDeployStrategy = async (strategy) => {
    try {
      setDeployingId(strategy.id)
      const deployResult = await apiService.deployStrategy(strategy.id)
      setSelectedStrategy(strategy)
      if (deployResult?.activeProfile) {
        setAiProfileModeValue(String(deployResult.activeProfile).toLowerCase())
      }
      if (deployResult?.regime) {
        setRegimeSnapshot(deployResult.regime)
      }
      toast.success(`${strategy.name} strategy deployed successfully!`)
    } catch (err) {
      if (isEndpointUnavailable(err)) {
        setSelectedStrategy(strategy)
        toast.info('Deploy endpoint backend belum tersedia. Strategy tetap dipilih pada UI.')
        return
      }
      toast.error(`Failed to deploy strategy: ${err.message}`)
    } finally {
      setDeployingId(null)
    }
  }

  const handleProfileModeChange = async (nextValue) => {
    const targetValue = String(nextValue || 'auto').toLowerCase()
    setSyncingProfileMode(true)
    try {
      const saved = await apiService.updateAIProfileMode(targetValue)
      const normalized = String(saved?.aiManualStrategyProfile || targetValue).toLowerCase()
      setAiProfileModeValue(normalized)

      const syncedRegime = await apiService.getAIRegimeStatus().catch(() => null)
      if (syncedRegime) {
        setRegimeSnapshot(syncedRegime)
      }

      if (normalized === 'auto') {
        toast.info('AI profile mode switched to Auto regime routing.')
      } else {
        toast.success(`AI profile locked to ${AI_PROFILE_LABELS[normalized] || normalized}.`)
      }
    } catch (err) {
      toast.error(`Failed to update AI profile mode: ${err.message}`)
    } finally {
      setSyncingProfileMode(false)
    }
  }

  const handleResetProfileMode = async () => {
    setSyncingProfileMode(true)
    try {
      const payload = await apiService.resetAIProfileOverride()
      setAiProfileModeValue('auto')
      if (payload?.regime) {
        setRegimeSnapshot(payload.regime)
      }
      toast.success('AI profile mode reset to Auto regime router.')
    } catch (err) {
      toast.error(`Failed to reset AI profile mode: ${err.message}`)
    } finally {
      setSyncingProfileMode(false)
    }
  }

  const handleBacktestStrategy = async (strategy) => {
    try {
      setBacktestingId(strategy.id)
      await apiService.backtestStrategy(strategy.id)
      toast.success(`${strategy.name} backtest started`)
    } catch (err) {
      if (isEndpointUnavailable(err)) {
        toast.info('Backtest endpoint backend belum tersedia saat ini.')
        return
      }
      toast.error(`Failed to start backtest: ${err.message}`)
    } finally {
      setBacktestingId(null)
    }
  }

  if (loading) {
    return (
      <div className="strategies-page">
        <h1>Strategy Builder</h1>
        <div className="strategies-grid">
          {[1, 2, 3].map((i) => (
            <CardSkeleton key={i} />
          ))}
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="strategies-page">
        <h1>Strategy Builder</h1>
        <div style={{
          textAlign: 'center',
          padding: '3rem',
          background: 'var(--card-bg)',
          borderRadius: '12px',
          border: '1px solid var(--accent-red)'
        }}>
          <p style={{ color: 'var(--accent-red)', marginBottom: '1rem' }}>❌ {error}</p>
          <Button 
            variant="primary"
            onClick={loadStrategies}
          >
            Try Again
          </Button>
        </div>
      </div>
    )
  }

  if (strategies.length === 0) {
    return (
      <div className="strategies-page">
        <h1>Strategy Builder</h1>
        <div style={{
          textAlign: 'center',
          padding: '3rem',
          background: 'var(--card-bg)',
          borderRadius: '12px'
        }}>
          <p style={{ color: 'var(--text-secondary)', marginBottom: '1rem' }}>No strategies available</p>
          <Button 
            variant="primary"
            onClick={loadStrategies}
          >
            Refresh
          </Button>
        </div>
      </div>
    )
  }

  const activeMode = aiProfileModeValue === 'auto' ? 'auto' : 'manual'
  const activeProfileLabel = AI_PROFILE_LABELS[aiProfileModeValue] || aiProfileModeValue
  const regimeLabel = String(regimeSnapshot?.regime || 'UNKNOWN').toUpperCase()
  const regimeProfile = String(regimeSnapshot?.strategyProfile || aiProfileModeValue || 'auto').toLowerCase()
  const regimeProfileLabel = AI_PROFILE_LABELS[regimeProfile] || regimeProfile

  return (
    <div className="strategies-page">
      <h1>Strategy Builder</h1>

      <section className="strategy-profile-panel">
        <div className="strategy-profile-main">
          <h2>AI Profile Mode</h2>
          <p>
            {activeMode === 'auto'
              ? 'Router otomatis memilih profile dari kondisi market terbaru.'
              : `Profile manual aktif: ${activeProfileLabel}.`}
          </p>
          <div className="strategy-profile-meta">
            <span className={`profile-mode-chip ${activeMode}`}>{activeMode.toUpperCase()}</span>
            <span className="profile-regime-chip">{`Regime ${regimeLabel}`}</span>
            <span className="profile-value-chip">{`Profile ${regimeProfileLabel}`}</span>
          </div>
        </div>

        <div className="strategy-profile-actions">
          <select
            value={aiProfileModeValue}
            onChange={(e) => handleProfileModeChange(e.target.value)}
            className="strategy-profile-select"
            disabled={syncingProfileMode}
          >
            {AI_PROFILE_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
          <button
            type="button"
            className="btn-secondary"
            onClick={handleResetProfileMode}
            disabled={syncingProfileMode || activeMode === 'auto'}
          >
            {syncingProfileMode ? 'Syncing...' : 'Reset Auto Router'}
          </button>
        </div>
      </section>

      <div className="strategies-grid">
        {strategies.map((strategy) => (
          <div
            key={strategy.id}
            className={`strategy-card ${selectedStrategy?.id === strategy.id ? 'selected' : ''}`}
            onClick={() => setSelectedStrategy(strategy)}
          >
            <div className="strategy-header">
              <div className="strategy-icon">{strategy.icon}</div>
              <div className="strategy-title">{strategy.name}</div>
            </div>
            <div className="strategy-desc">{strategy.desc}</div>

            <div className="strategy-metrics">
              <div className="metric">
                <span className="label">Expected Return</span>
                <span className="value">{strategy.expectedReturn}</span>
              </div>
              <div className="metric">
                <span className="label">Sharpe Ratio</span>
                <span className="value">{strategy.sharpeRatio}</span>
              </div>
              <div className="metric">
                <span className="label">Max Drawdown</span>
                <span className="value">{strategy.maxDrawdown}</span>
              </div>
            </div>

            <Button 
              variant="primary" 
              size="md"
              onClick={() => handleDeployStrategy(strategy)}
              loading={deployingId === strategy.id}
            >
              {deployingId === strategy.id ? 'Deploying...' : 'Deploy Strategy'}
            </Button>
          </div>
        ))}
      </div>

      {selectedStrategy && (
        <div className="strategy-details">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem' }}>
            <h2>📋 {selectedStrategy.name} Strategy Rules</h2>
            <div style={{ display: 'flex', gap: '1rem' }}>
              <Button 
                variant="success" 
                icon={<span>🚀</span>}
                onClick={() => handleDeployStrategy(selectedStrategy)}
                loading={deployingId === selectedStrategy.id}
              >
                {deployingId === selectedStrategy.id ? 'Activating...' : 'Activate Now'}
              </Button>
              <Button 
                variant="secondary"
                onClick={() => handleBacktestStrategy(selectedStrategy)}
                loading={backtestingId === selectedStrategy.id}
              >
                {backtestingId === selectedStrategy.id ? 'Starting...' : 'Run Backtest'}
              </Button>
            </div>
          </div>
          <div className="rules-list">
            {selectedStrategy.rules.map((rule, idx) => (
              <div key={idx} className="rule-item">
                <span className="rule-number">{idx + 1}</span>
                <span className="rule-text">{rule}</span>
              </div>
            ))}
          </div>

          {/* Backtest Results */}
          <div className="backtest-section">
            <h3>📊 Backtest Results (2023-2025)</h3>
            <div className="backtest-stats">
              <div className="stat">
                <span>Total Return</span>
                <span className="value positive">+45.2%</span>
              </div>
              <div className="stat">
                <span>Win Rate</span>
                <span className="value">62%</span>
              </div>
              <div className="stat">
                <span>Winning Trades</span>
                <span className="value positive">124</span>
              </div>
              <div className="stat">
                <span>Losing Trades</span>
                <span className="value negative">76</span>
              </div>
              <div className="stat">
                <span>Profit Factor</span>
                <span className="value">1.8x</span>
              </div>
              <div className="stat">
                <span>Avg Trade Value</span>
                <span className="value positive">+2.4%</span>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
