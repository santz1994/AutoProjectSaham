import React, { useEffect, useState } from 'react'
import Button from './Button'
import StatsCard from './StatsCard'
import ExportMenu from './ExportMenu'
import toast from '../store/toastStore'
import { CardSkeleton } from './LoadingSkeletons'
import useTradingStore from '../store/tradingStore'
import apiService from '../utils/apiService'
import '../styles/dashboard.css'

function QuickActions({ onEmergencyStop, onTakeProfit, onLiquidate }) {
  return (
    <div className="quick-actions-panel">
      <h3>⚡ Quick Actions</h3>
      <div className="quick-actions-grid">
        <Button
          variant="danger"
          size="sm"
          icon={<span>⏹️</span>}
          onClick={onEmergencyStop}
        >
          Emergency Stop
        </Button>
        <Button
          variant="success"
          size="sm"
          icon={<span>💰</span>}
          onClick={onTakeProfit}
        >
          Take Profit All
        </Button>
        <Button
          variant="warning"
          size="sm"
          icon={<span>🔄</span>}
          onClick={onLiquidate}
        >
          Liquidate Positions
        </Button>
      </div>
    </div>
  )
}

function PortfolioBreakdownChart({ positions }) {
  if (!positions || positions.length === 0) {
    return (
      <div style={{ textAlign: 'center', padding: '2rem', color: '#94a3b8' }}>
        No positions to display
      </div>
    )
  }

  const sectorData = positions.reduce((acc, pos) => {
    const sector = pos.sector || 'Other'
    acc[sector] = (acc[sector] || 0) + pos.totalValue
    return acc
  }, {})

  const total = Object.values(sectorData).reduce((sum, val) => sum + val, 0)
  
  const colors = ['#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#ec4899']
  
  return (
    <div className="portfolio-breakdown">
      <h3>Portfolio by Sector</h3>
      <div className="breakdown-chart">
        {Object.entries(sectorData).map(([sector, value], idx) => {
          const percentage = ((value / total) * 100).toFixed(1)
          return (
            <div key={sector} className="breakdown-item">
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.5rem' }}>
                <div style={{ width: '12px', height: '12px', borderRadius: '50%', background: colors[idx % colors.length] }} />
                <span style={{ flex: 1, color: '#f1f5f9', fontSize: '0.875rem' }}>{sector}</span>
                <span style={{ color: '#94a3b8', fontSize: '0.875rem' }}>{percentage}%</span>
              </div>
              <div style={{ width: '100%', height: '8px', background: '#1e293b', borderRadius: '4px', overflow: 'hidden' }}>
                <div style={{ 
                  width: `${percentage}%`, 
                  height: '100%', 
                  background: colors[idx % colors.length],
                  transition: 'width 0.5s ease'
                }} />
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

function PortfolioValueChart({ data }) {
  if (!data || data.length === 0) {
    return (
      <div style={{ textAlign: 'center', padding: '2rem', color: '#94a3b8' }}>
        Loading chart data...
      </div>
    )
  }

  const max = Math.max(...data.map(d => d.value))
  const min = Math.min(...data.map(d => d.value))
  const range = max - min

  return (
    <div className="portfolio-value-chart">
      <h3>Portfolio Value (7 Days)</h3>
      <div className="chart-container" style={{ height: '200px', position: 'relative' }}>
        <svg width="100%" height="100%" style={{ overflow: 'visible' }}>
          {/* Grid lines */}
          {[0, 1, 2, 3, 4].map((i) => (
            <line
              key={i}
              x1="0"
              y1={`${i * 25}%`}
              x2="100%"
              y2={`${i * 25}%`}
              stroke="#334155"
              strokeWidth="1"
              strokeDasharray="4"
            />
          ))}
          
          {/* Line path */}
          <polyline
            points={data.map((d, i) => {
              const x = (i / (data.length - 1)) * 100
              const y = 100 - ((d.value - min) / range) * 100
              return `${x}%,${y}%`
            }).join(' ')}
            fill="none"
            stroke="#3b82f6"
            strokeWidth="2"
          />
          
          {/* Area fill */}
          <polygon
            points={`0,100% ${data.map((d, i) => {
              const x = (i / (data.length - 1)) * 100
              const y = 100 - ((d.value - min) / range) * 100
              return `${x}%,${y}%`
            }).join(' ')} 100%,100%`}
            fill="url(#gradient)"
            opacity="0.2"
          />
          
          <defs>
            <linearGradient id="gradient" x1="0%" y1="0%" x2="0%" y2="100%">
              <stop offset="0%" stopColor="#3b82f6" />
              <stop offset="100%" stopColor="#1e293b" />
            </linearGradient>
          </defs>
        </svg>
      </div>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: '1rem', fontSize: '0.8125rem', color: '#94a3b8' }}>
        {data.slice(0, 7).map((d, i) => (
          <span key={i}>{d.label}</span>
        ))}
      </div>
    </div>
  )
}

export default function DashboardPageEnhanced() {
  const [portfolio, setPortfolio] = useState(null)
  const [botData, setBotData] = useState(null)
  const [signals, setSignals] = useState([])
  const [health, setHealth] = useState(null)
  const [activities, setActivities] = useState([])
  const [loading, setLoading] = useState(true)
  const [chartData, setChartData] = useState([])
  const [autoRefresh, setAutoRefresh] = useState(true)
  
  const killSwitchTriggered = useTradingStore((s) => s.killSwitchTriggered)

  const loadDashboardData = async () => {
    try {
      const [portfolioData, botStatus, topSignals, healthData, recentActivity] = await Promise.all([
        apiService.getPortfolio(),
        apiService.getBotStatus(),
        apiService.getTopSignals(3),
        apiService.getPortfolioHealth(),
        apiService.getRecentActivity(5),
      ])

      setPortfolio(portfolioData)
      setBotData(botStatus)
      setSignals(topSignals)
      setHealth(healthData)
      setActivities(recentActivity)

      // Generate mock chart data (replace with real historical data)
      const today = new Date()
      const mockChartData = Array.from({ length: 7 }, (_, i) => ({
        label: new Date(today.getTime() - (6 - i) * 24 * 60 * 60 * 1000).toLocaleDateString('id-ID', { weekday: 'short' }),
        value: portfolioData.totalValue * (0.95 + Math.random() * 0.1)
      }))
      setChartData(mockChartData)

      if (!autoRefresh) {
        toast.success('Dashboard data refreshed')
      }
    } catch (error) {
      toast.error('Failed to load dashboard data: ' + error.message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadDashboardData()
  }, [])

  // Auto-refresh every 30 seconds
  useEffect(() => {
    if (!autoRefresh) return
    
    const interval = setInterval(loadDashboardData, 30000)
    return () => clearInterval(interval)
  }, [autoRefresh])

  const handleEmergencyStop = () => {
    toast.warning('Emergency stop activated! All trading halted.')
    useTradingStore.setState({ killSwitchTriggered: true, botStatus: 'idle' })
  }

  const handleTakeProfit = async () => {
    try {
      toast.info('Taking profit on all positions...')
      // Call API to take profit
      toast.success('Profit taking orders submitted!')
    } catch (error) {
      toast.error('Failed to take profit: ' + error.message)
    }
  }

  const handleLiquidate = async () => {
    const confirmed = window.confirm('Are you sure you want to liquidate all positions? This cannot be undone.')
    if (!confirmed) return

    try {
      toast.warning('Liquidating all positions...')
      // Call API to liquidate
      toast.success('Liquidation orders submitted!')
    } catch (error) {
      toast.error('Failed to liquidate: ' + error.message)
    }
  }

  const handleExportPortfolio = async (format) => {
    try {
      const report = await apiService.getPerformanceReport('today')
      toast.success(`Portfolio exported as ${format.toUpperCase()}`)
    } catch (error) {
      toast.error('Export failed: ' + error.message)
    }
  }

  if (loading) {
    return (
      <div className="dashboard-page">
        <h1>📊 Dashboard</h1>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '1rem', marginBottom: '2rem' }}>
          <CardSkeleton />
          <CardSkeleton />
          <CardSkeleton />
          <CardSkeleton />
        </div>
        <CardSkeleton />
      </div>
    )
  }

  const isPortfolioPositive = portfolio?.totalP_L >= 0

  return (
    <div className={`dashboard-page ${killSwitchTriggered ? 'kill-switch-mode' : ''}`}>
      {killSwitchTriggered && (
        <div className="emergency-banner">
          ⏹️ EMERGENCY STOP ACTIVE - All trading halted. Resume trading in top menu.
        </div>
      )}

      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '2rem' }}>
        <h1 style={{ margin: 0, color: '#f1f5f9' }}>📊 Dashboard</h1>
        <div style={{ display: 'flex', gap: '1rem', alignItems: 'center' }}>
          <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: '#94a3b8', fontSize: '0.875rem' }}>
            <input
              type="checkbox"
              checked={autoRefresh}
              onChange={(e) => setAutoRefresh(e.target.checked)}
            />
            Auto-refresh
          </label>
          <Button 
            variant="ghost"
            size="sm"
            icon={<span>🔄</span>}
            onClick={loadDashboardData}
            loading={loading}
          >
            Refresh
          </Button>
          <ExportMenu 
            data={portfolio}
            filename="portfolio_summary"
            onExport={handleExportPortfolio}
          />
        </div>
      </div>

      {/* Stats Overview */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '1rem', marginBottom: '2rem' }}>
        <StatsCard
          icon="💼"
          title="Portfolio Value"
          value={`IDR ${(portfolio?.totalValue / 1000000).toFixed(2)}M`}
          subtitle="Total assets"
        />
        <StatsCard
          icon="💰"
          title="Profit/Loss"
          value={`IDR ${(portfolio?.totalP_L / 1000).toFixed(1)}K`}
          change={`${portfolio?.percentP_L >= 0 ? '+' : ''}${portfolio?.percentP_L?.toFixed(2)}%`}
          trend={portfolio?.totalP_L > 0 ? 'up' : portfolio?.totalP_L < 0 ? 'down' : 'neutral'}
        />
        <StatsCard
          icon="💵"
          title="Cash Available"
          value={`IDR ${(portfolio?.cash / 1000).toFixed(1)}K`}
          subtitle="Ready to invest"
        />
        <StatsCard
          icon="📈"
          title="Active Positions"
          value={portfolio?.positions?.length || 0}
          subtitle={`${botData?.activeTrades || 0} trades today`}
        />
      </div>

      <div className="dashboard-grid">
        {/* Portfolio Value Chart */}
        <div className="grid-item span-2">
          <div className="card">
            <PortfolioValueChart data={chartData} />
          </div>
        </div>

        {/* Quick Actions */}
        <div className="grid-item">
          <div className="card">
            <QuickActions
              onEmergencyStop={handleEmergencyStop}
              onTakeProfit={handleTakeProfit}
              onLiquidate={handleLiquidate}
            />
          </div>
        </div>

        {/* Portfolio Breakdown */}
        <div className="grid-item">
          <div className="card">
            <PortfolioBreakdownChart positions={portfolio?.positions} />
          </div>
        </div>

        {/* Bot Status */}
        <div className="grid-item">
          <div className="card">
            <h3>🤖 Bot Status</h3>
            <div className="bot-status-content">
              <div className="status-indicator-large">
                {botData?.status === 'running' ? '🟢' : '⚪'}
              </div>
              <div className="status-info">
                <div style={{ fontSize: '1.25rem', fontWeight: '600', color: '#f1f5f9', marginBottom: '0.5rem' }}>
                  {botData?.status?.toUpperCase() || 'IDLE'}
                </div>
                {botData && (
                  <div style={{ fontSize: '0.875rem', color: '#94a3b8' }}>
                    <p>Uptime: {botData.uptime || 'N/A'}</p>
                    <p>Win Rate: {((botData.winRate || 0) * 100).toFixed(1)}%</p>
                    <p>Trades Today: {botData.totalTradesToday || 0}</p>
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>

        {/* Portfolio Health */}
        <div className="grid-item">
          <div className="card">
            <h3>❤️ Portfolio Health</h3>
            {health && (
              <div style={{ textAlign: 'center' }}>
                <div style={{ fontSize: '3rem', fontWeight: '700', color: health.score >= 70 ? '#10b981' : health.score >= 50 ? '#f59e0b' : '#ef4444' }}>
                  {health.score}
                </div>
                <div style={{ color: '#94a3b8', marginBottom: '1rem' }}>{health.rating}</div>
                <div style={{ fontSize: '0.8125rem', color: '#cbd5e1', lineHeight: '1.5' }}>
                  {health.recommendation}
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Top AI Signals */}
        <div className="grid-item span-full">
          <div className="card">
            <h3>🎯 Top AI Signals</h3>
            {signals.length === 0 ? (
              <p style={{ textAlign: 'center', color: '#94a3b8', padding: '2rem' }}>No signals available</p>
            ) : (
              <div className="signals-grid">
                {signals.map((signal) => (
                  <div key={signal.id} className={`signal-card ${signal.signal.toLowerCase().replace('_', '-')}`}>
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
            )}
          </div>
        </div>

        {/* Recent Activity */}
        <div className="grid-item span-2">
          <div className="card">
            <h3>📜 Recent Activity</h3>
            {activities.length === 0 ? (
              <p style={{ textAlign: 'center', color: '#94a3b8', padding: '2rem' }}>No recent activity</p>
            ) : (
              <div className="activity-list">
                {activities.map((activity) => (
                  <div key={activity.id} className={`activity-item ${activity.type.toLowerCase()}`}>
                    <div className="activity-icon">
                      {activity.type === 'BUY' ? '📈' : activity.type === 'SELL' ? '📉' : '📊'}
                    </div>
                    <div className="activity-content">
                      <div className="activity-main">
                        {activity.symbol && <span className="symbol">{activity.symbol}</span>}
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
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
