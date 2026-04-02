import React, { useEffect, useState } from 'react'
import Button from './Button'
import toast from '../store/toastStore'
import { CardSkeleton } from './LoadingSkeletons'
import useTradingStore from '../store/tradingStore'
import {
  mockPortfolioData,
  mockBotStatus,
  mockTopSignals,
  mockPortfolioHealthScore,
  mockRecentActivity,
} from '../utils/mockData'
import '../styles/dashboard.css'

function PortfolioCard() {
  const [loading, setLoading] = useState(true)
  const { portfolio, setPortfolio } = useTradingStore((s) => ({
    portfolio: s.portfolio,
    setPortfolio: s.setPortfolio,
  }))

  useEffect(() => {
    // Simulate loading
    setLoading(true)
    setTimeout(() => {
      setPortfolio(mockPortfolioData)
      setLoading(false)
      toast.success('Portfolio data loaded')
    }, 1000)
  }, [])

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
          onClick={() => {
            setLoading(true)
            setTimeout(() => {
              setLoading(false)
              toast.success('Portfolio refreshed!')
            }, 500)
          }}
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
  const botStatus = useTradingStore((s) => s.botStatus)
  const killSwitchTriggered = useTradingStore((s) => s.killSwitchTriggered)

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
          <div className="status-meta">
            <p>Uptime: {mockBotStatus.uptime}</p>
            <p>Active Trades: {mockBotStatus.activeTrades}</p>
            <p>Today Win Rate: {(mockBotStatus.winRate * 100).toFixed(1)}%</p>
          </div>
        </div>
      </div>
    </div>
  )
}

function HealthScoreWidget() {
  const portfolioHealthScore = useTradingStore((s) => s.portfolioHealthScore)
  const health = mockPortfolioHealthScore

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
          <div className="factor">
            <label>Diversification</label>
            <div className="bar">
              <span style={{ width: `${health.factors.diversification}%` }}></span>
            </div>
          </div>
          <div className="factor">
            <label>Risk Balance</label>
            <div className="bar">
              <span style={{ width: `${health.factors.riskBalance}%` }}></span>
            </div>
          </div>
          <div className="factor">
            <label>Profitability</label>
            <div className="bar">
              <span style={{ width: `${health.factors.profitability}%` }}></span>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

function TopSignalsWidget() {
  const signals = mockTopSignals.slice(0, 3)

  return (
    <div className="card signals-card">
      <h2>Top AI Signals 🎯</h2>
      <div className="signals-list">
        {signals.map((signal) => (
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
        ))}
      </div>
    </div>
  )
}

function RecentActivityWidget() {
  const activities = mockRecentActivity.slice(0, 5)

  return (
    <div className="card activity-card">
      <h2>Recent Activity</h2>
      <div className="activity-list">
        {activities.map((activity) => (
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
        ))}
      </div>
    </div>
  )
}

export default function DashboardPage() {
  const killSwitchTriggered = useTradingStore((s) => s.killSwitchTriggered)

  return (
    <div className={`dashboard-page ${killSwitchTriggered ? 'kill-switch-mode' : ''}`}>
      {killSwitchTriggered && (
        <div className="emergency-banner">
          ⏹️ EMERGENCY STOP ACTIVE - All trading halted. Resume trading in top menu.
        </div>
      )}

      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '2rem' }}>
        <h1 style={{ margin: 0, color: '#f1f5f9' }}>Dashboard</h1>
        <div style={{ display: 'flex', gap: '1rem' }}>
          <Button 
            variant="primary" 
            icon={<span>📊</span>}
            onClick={() => toast.info('Performance report generated')}
          >
            Performance Report
          </Button>
          <Button 
            variant="secondary"
            icon={<span>⚙️</span>}
            onClick={() => toast.info('Opening settings...')}
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
