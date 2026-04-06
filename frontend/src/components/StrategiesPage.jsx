import React, { useState, useEffect } from 'react'
import Button from './Button'
import toast from '../store/toastStore'
import { CardSkeleton } from './LoadingSkeletons'
import apiService from '../utils/apiService'
import '../styles/strategies.css'

export default function StrategiesPage() {
  const [selectedStrategy, setSelectedStrategy] = useState(null)
  const [strategies, setStrategies] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [deployingId, setDeployingId] = useState(null)
  const [backtestingId, setBacktestingId] = useState(null)

  const loadStrategies = async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await apiService.getStrategies()
      setStrategies(data)
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
      await apiService.deployStrategy(strategy.id)
      setSelectedStrategy(strategy)
      toast.success(`${strategy.name} strategy deployed successfully!`)
    } catch (err) {
      toast.error(`Failed to deploy strategy: ${err.message}`)
    } finally {
      setDeployingId(null)
    }
  }

  const handleBacktestStrategy = async (strategy) => {
    try {
      setBacktestingId(strategy.id)
      await apiService.backtestStrategy(strategy.id)
      toast.success(`${strategy.name} backtest started`)
    } catch (err) {
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
          background: '#1a1a1a',
          borderRadius: '12px',
          border: '1px solid #ff6b6b'
        }}>
          <p style={{ color: '#ff6b6b', marginBottom: '1rem' }}>❌ {error}</p>
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
          background: '#1a1a1a',
          borderRadius: '12px'
        }}>
          <p style={{ color: '#999', marginBottom: '1rem' }}>No strategies available</p>
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

  return (
    <div className="strategies-page">
      <h1>Strategy Builder</h1>

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
