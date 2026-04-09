import React, { useEffect, useState } from 'react'
import Button from './Button'
import toast from '../store/toastStore'
import { CardSkeleton } from './LoadingSkeletons'
import useTradingStore from '../store/tradingStore'
import apiService from '../utils/apiService'
import '../styles/dashboard.css'

function PortfolioCard() {
  const [loading, setLoading] = useState(true)
  const { portfolio, setPortfolio } = useTradingStore((s) => ({
    portfolio: s.portfolio,
    setPortfolio: s.setPortfolio,
  }))

  const loadPortfolio = async ({ showSuccessToast = false } = {}) => {
    setLoading(true)
    try {
      const data = await apiService.getPortfolio()
      setPortfolio(data)
      if (showSuccessToast) {
        toast.success('Portfolio data refreshed')
      }
    } catch (error) {
      toast.error('Failed to load portfolio: ' + error.message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadPortfolio()
  }, [])

  const handleRefresh = async () => {
    try {
      await apiService.refreshPortfolio()
      await loadPortfolio({ showSuccessToast: true })
    } catch (error) {
      toast.error('Failed to refresh portfolio: ' + error.message)
    }
  }

  if (loading) {
    return <CardSkeleton />
  }

  const isPositive = portfolio.totalP_L >= 0

  return (
    <div className="card portfolio-card">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
        <h2>Portfolio Summary</h2>
        <Button 
          variant="ghost" 
          size="sm"
          icon={<span>🔄</span>}
          onClick={handleRefresh}
        >
          Refresh
        </Button>
      </div>
      <div className="portfolio-grid">
        <div className="portfolio-item">
          <label>Total Value</label>
          <div className="value">IDR {(portfolio.totalValue / 1000000).toFixed(2)}M</div>
        </div>
        <div className="portfolio-item">
          <label>Profit/Loss</label>
          <div className={`value ${isPositive ? 'positive' : 'negative'}`}>
            IDR {(portfolio.totalP_L / 1000).toFixed(0)}K
            <span className="percentage"> ({portfolio.percentP_L?.toFixed(2)}%)</span>
          </div>
        </div>
        <div className="portfolio-item">
          <label>Cash Available</label>
          <div className="value">IDR {(portfolio.cash / 1000).toFixed(0)}K</div>
        </div>
        <div className="portfolio-item">
          <label>Positions</label>
          <div className="value">{portfolio.positions?.length || 0} Active</div>
        </div>
      </div>
    </div>
  )
}

function BotStatusCard() {
  const [botData, setBotData] = useState(null)
  const botStatus = useTradingStore((s) => s.botStatus)
  const killSwitchTriggered = useTradingStore((s) => s.killSwitchTriggered)
  const setBotStatus = useTradingStore((s) => s.setBotStatus)
  const setKillSwitchState = useTradingStore((s) => s.setKillSwitchState)

  useEffect(() => {
    const loadBotStatus = async () => {
      try {
        const data = await apiService.getBotStatus()
        setBotData(data)
        if (data?.status) {
          setBotStatus(String(data.status).toLowerCase())
        }
        if (typeof data?.killSwitchActive === 'boolean') {
          setKillSwitchState(Boolean(data.killSwitchActive), data?.lastTradeTime || null)
        }
      } catch (error) {
        console.error('Failed to load bot status:', error)
      }
    }
    loadBotStatus()
    
    // Refresh every 10 seconds
    const interval = setInterval(loadBotStatus, 10000)
    return () => clearInterval(interval)
  }, [])

  return (
    <div className={`card bot-status-card ${killSwitchTriggered ? 'disabled' : ''}`}>
      <h2>Bot Status</h2>
      <div className="status-content">
        <div className={`status-indicator ${botStatus}`}>
          <span className="pulse"></span>
          {botStatus === 'running' ? '🟢' : botStatus === 'paused' ? '🟡' : '⚪'}
        </div>
        <div className="status-details">
          <div className="status-main">
            {botStatus.toUpperCase()}
            {killSwitchTriggered && <span className="emergency-badge">EMERGENCY STOP ACTIVE</span>}
          </div>
          {botData && (
            <div className="status-meta">
              <p>Uptime: {botData.uptime || 'N/A'}</p>
              <p>Active Trades: {botData.activeTrades || 0}</p>
              <p>Today Win Rate: {((botData.winRate || 0) * 100).toFixed(1)}%</p>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

function HealthScoreWidget() {
  const [health, setHealth] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const loadHealth = async () => {
      try {
        const data = await apiService.getPortfolioHealth()
        setHealth(data)
      } catch (error) {
        console.error('Failed to load portfolio health:', error)
      } finally {
        setLoading(false)
      }
    }
    loadHealth()
  }, [])

  if (loading || !health) {
    return <CardSkeleton />
  }

  return (
    <div className="card health-score-card">
      <h2>Portfolio Health</h2>
      <div className="health-score-content">
        <div className="health-score-circle">
          <svg viewBox="0 0 120 120">
            <circle cx="60" cy="60" r="55" className="bg" />
            <circle
              cx="60"
              cy="60"
              r="55"
              className="progress"
              style={{
                strokeDasharray: `${(health.score / 100) * (2 * Math.PI * 55)} ${2 * Math.PI * 55}`,
              }}
            />
          </svg>
          <div className="score-text">
            <span className="number">{health.score}</span>
            <span className="label">Score</span>
          </div>
        </div>
        <div className="health-factors">
          {health.factors && Object.entries(health.factors).slice(0, 3).map(([key, value]) => (
            <div className="factor" key={key}>
              <label>{key.charAt(0).toUpperCase() + key.slice(1).replace(/([A-Z])/g, ' $1')}</label>
              <div className="bar">
                <span style={{ width: `${value}%` }}></span>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

function ExecutionQueueWidget() {
  const [snapshot, setSnapshot] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let active = true

    const loadExecutionQueue = async () => {
      try {
        const data = await apiService.getExecutionPendingOrders(20)
        if (active) {
          setSnapshot(data)
        }
      } catch (error) {
        if (active) {
          console.error('Failed to load execution queue snapshot:', error)
        }
      } finally {
        if (active) {
          setLoading(false)
        }
      }
    }

    loadExecutionQueue()
    const interval = setInterval(loadExecutionQueue, 8000)

    return () => {
      active = false
      clearInterval(interval)
    }
  }, [])

  if (loading) {
    return <CardSkeleton />
  }

  const total = Number(snapshot?.total || 0)
  const managerReady = Boolean(snapshot?.execution?.available)
  const sampleOrders = Array.isArray(snapshot?.pendingOrders) ? snapshot.pendingOrders.slice(0, 3) : []

  return (
    <div className="card execution-queue-card">
      <h2>Execution Queue</h2>
      <div className="queue-summary">
        <div className="queue-metric">
          <label>Pending Orders</label>
          <div className="value">{total}</div>
        </div>
        <div className="queue-metric">
          <label>Manager</label>
          <div className={`state ${managerReady ? 'ready' : 'offline'}`}>
            {managerReady ? 'READY' : 'OFFLINE'}
          </div>
        </div>
      </div>
      <div className="queue-orders">
        {sampleOrders.length === 0 ? (
          <p className="queue-empty">No pending orders in runtime queue.</p>
        ) : (
          sampleOrders.map((order) => (
            <div key={order.order_id || `${order.symbol}-${order.side}`} className="queue-order-item">
              <span>{order.symbol || 'UNKNOWN'}</span>
              <span>{String(order.side || '-').toUpperCase()}</span>
              <span>{order.qty || 0}</span>
            </div>
          ))
        )}
      </div>
    </div>
  )
}

function QuotaUsageWidget() {
  const [snapshot, setSnapshot] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let active = true

    const loadQuotaUsage = async () => {
      try {
        const data = await apiService.getQuotaUsage('self')
        if (active) {
          setSnapshot(data)
        }
      } catch (error) {
        if (active) {
          console.error('Failed to load quota usage:', error)
        }
      } finally {
        if (active) {
          setLoading(false)
        }
      }
    }

    loadQuotaUsage()
    const interval = setInterval(loadQuotaUsage, 15000)

    return () => {
      active = false
      clearInterval(interval)
    }
  }, [])

  if (loading) {
    return <CardSkeleton />
  }

  const usage = snapshot?.usage || {}
  const requests = usage.requests || {}
  const limits = usage.limits || {}
  const utilization = usage.utilizationPercent || {}
  const tier = String(usage.tier || 'free').toUpperCase()

  return (
    <div className="card quota-usage-card">
      <h2>API Quota Usage</h2>
      <div className="quota-tier">Tier: {tier}</div>

      <div className="quota-grid">
        <div className="quota-item">
          <label>Last Minute</label>
          <div className="value">{requests.lastMinute || 0} / {limits.perMinute || 0}</div>
          <small>{(utilization.minute || 0).toFixed(2)}%</small>
        </div>
        <div className="quota-item">
          <label>Last Hour</label>
          <div className="value">{requests.lastHour || 0} / {limits.perHour || 0}</div>
          <small>{(utilization.hour || 0).toFixed(2)}%</small>
        </div>
      </div>
    </div>
  )
}

function TopSignalsWidget() {
  const [signals, setSignals] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const loadSignals = async () => {
      try {
        const data = await apiService.getTopSignals(3)
        setSignals(data)
      } catch (error) {
        console.error('Failed to load signals:', error)
      } finally {
        setLoading(false)
      }
    }
    loadSignals()
  }, [])

  if (loading) {
    return <CardSkeleton />
  }

  return (
    <div className="card signals-card">
      <h2>Top AI Signals 🎯</h2>
      <div className="signals-list">
        {signals.length === 0 ? (
          <p style={{ color: 'var(--text-secondary)', textAlign: 'center', padding: '2rem' }}>
            No signals available at the moment
          </p>
        ) : (
          signals.map((signal) => (
            <div key={signal.id} className={`signal-item ${signal.signal.toLowerCase().replace('_', '-')}`}>
              <div className="signal-header">
                <span className="symbol">{signal.symbol}</span>
                <span className={`signal-badge ${signal.signal.toLowerCase().replace('_', '-')}`}>
                  {signal.signal.replace('_', ' ')}
                </span>
              </div>
              <div className="signal-body">
                <p className="reason">📊 {signal.reason}</p>
                <div className="signal-meta">
                  <span>Confidence: {(signal.confidence * 100).toFixed(0)}%</span>
                  <span className="target">Target: {signal.predictedMove}</span>
                </div>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  )
}

function RecentActivityWidget() {
  const [activities, setActivities] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const loadActivity = async () => {
      try {
        const data = await apiService.getRecentActivity(5)
        setActivities(data)
      } catch (error) {
        console.error('Failed to load activity:', error)
      } finally {
        setLoading(false)
      }
    }
    loadActivity()
  }, [])

  if (loading) {
    return <CardSkeleton />
  }

  return (
    <div className="card activity-card">
      <h2>Recent Activity</h2>
      <div className="activity-list">
        {activities.length === 0 ? (
          <p style={{ color: 'var(--text-secondary)', textAlign: 'center', padding: '2rem' }}>
            No recent activity
          </p>
        ) : (
          activities.map((activity) => (
            <div key={activity.id} className={`activity-item ${activity.type.toLowerCase()}`}>
              <div className="activity-icon">
                {activity.type === 'BUY' ? '📈' : activity.type === 'SELL' ? '📉' : '📊'}
              </div>
              <div className="activity-content">
                <div className="activity-main">
                  {activity.symbol && (
                    <span className="symbol">{activity.symbol}</span>
                  )}
                  <span className="message">{activity.message || `${activity.type} ${activity.quantity} units`}</span>
                </div>
                <div className="activity-meta">
                  <small>{new Date(activity.timestamp).toLocaleTimeString('id-ID')}</small>
                </div>
              </div>
              <div className={`status-badge ${activity.status.toLowerCase()}`}>{activity.status}</div>
            </div>
          ))
        )}
      </div>
    </div>
  )
}

export default function DashboardPage({ onNavigate }) {
  const killSwitchTriggered = useTradingStore((s) => s.killSwitchTriggered)

  const handleGenerateReport = async () => {
    try {
      toast.info('Generating performance report...')
      const report = await apiService.getPerformanceReport('today')
      toast.success('Performance report ready!')
      // Could open a modal or download the report here
      console.log('Performance Report:', report)
    } catch (error) {
      toast.error('Failed to generate report: ' + error.message)
    }
  }

  const handleOpenBotSettings = () => {
    if (typeof onNavigate === 'function') {
      onNavigate('settings')
      return
    }
    toast.info('Open Settings to configure bot behavior.')
  }

  return (
    <div className={`dashboard-page ${killSwitchTriggered ? 'kill-switch-mode' : ''}`}>
      {killSwitchTriggered && (
        <div className="emergency-banner">
          ⏹️ EMERGENCY STOP ACTIVE - All trading halted. Resume trading in top menu.
        </div>
      )}

      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '2rem' }}>
        <h1 style={{ margin: 0, color: 'var(--text-primary)' }}>Dashboard</h1>
        <div style={{ display: 'flex', gap: '1rem' }}>
          <Button 
            variant="primary" 
            icon={<span>📊</span>}
            onClick={handleGenerateReport}
          >
            Performance Report
          </Button>
          <Button 
            variant="secondary"
            icon={<span>⚙️</span>}
            onClick={handleOpenBotSettings}
          >
            Bot Settings
          </Button>
        </div>
      </div>

      <div className="dashboard-grid">
        <div className="grid-item span-full">
          <PortfolioCard />
        </div>

        <div className="grid-item span-2">
          <BotStatusCard />
        </div>

        <div className="grid-item">
          <HealthScoreWidget />
        </div>

        <div className="grid-item">
          <ExecutionQueueWidget />
        </div>

        <div className="grid-item">
          <QuotaUsageWidget />
        </div>

        <div className="grid-item span-full">
          <TopSignalsWidget />
        </div>

        <div className="grid-item span-2">
          <RecentActivityWidget />
        </div>
      </div>
    </div>
  )
}
