import React, { useState, useMemo, useEffect } from 'react'
import Button from './Button'
import toast from '../store/toastStore'
import { CardSkeleton } from './LoadingSkeletons'
import apiService from '../utils/apiService'
import '../styles/tradelogs.css'

function toNumber(value, fallback = 0) {
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : fallback
}

function parseDurationToMinutes(value) {
  if (typeof value === 'number') return value
  if (!value || typeof value !== 'string') return 0

  const cleaned = value.toLowerCase().trim()
  const dayMatch = cleaned.match(/(\d+)\s*d/)
  const hourMatch = cleaned.match(/(\d+)\s*h/)
  const minuteMatch = cleaned.match(/(\d+)\s*m/)

  const days = dayMatch ? Number(dayMatch[1]) : 0
  const hours = hourMatch ? Number(hourMatch[1]) : 0
  const minutes = minuteMatch ? Number(minuteMatch[1]) : 0

  if (days || hours || minutes) {
    return days * 24 * 60 + hours * 60 + minutes
  }

  const numeric = Number(cleaned)
  return Number.isFinite(numeric) ? numeric : 0
}

function normalizeTrade(trade, index) {
  const quantity = toNumber(trade.quantity, 0)
  const entryPrice = toNumber(trade.entryPrice ?? trade.price, 0)
  const exitPrice = toNumber(trade.exitPrice ?? (trade.type === 'SELL' ? trade.price : 0), 0)

  let profit = toNumber(trade.profit, Number.NaN)
  if (!Number.isFinite(profit)) {
    if (entryPrice > 0 && exitPrice > 0 && quantity > 0) {
      profit = (exitPrice - entryPrice) * quantity
    } else {
      profit = 0
    }
  }

  let profitPct = toNumber(trade.profitPct, Number.NaN)
  if (!Number.isFinite(profitPct)) {
    const invested = entryPrice * quantity
    profitPct = invested > 0 ? (profit / invested) * 100 : 0
  }

  return {
    id: trade.id ?? `${trade.symbol || 'trade'}-${index}`,
    symbol: trade.symbol || '-',
    type: String(trade.type || 'BUY').toUpperCase(),
    quantity,
    entryPrice,
    exitPrice,
    profit,
    profitPct,
    date: trade.date || trade.timestamp || new Date().toISOString(),
    duration: trade.duration || '-',
    status: String(trade.status || 'UNKNOWN').toUpperCase(),
  }
}

export default function TradeLogsPage() {
  const [filterType, setFilterType] = useState('all')
  const [sortBy, setSortBy] = useState('date')
  const [trades, setTrades] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const loadTradeLogs = async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await apiService.getTradeLogs()
      setTrades(Array.isArray(data) ? data : [])
    } catch (err) {
      const errorMsg = err.message || 'Failed to load trade logs'
      setError(errorMsg)
      toast.error(errorMsg)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadTradeLogs()
  }, [])

  const normalizedTrades = useMemo(
    () => trades.map((trade, index) => normalizeTrade(trade, index)),
    [trades]
  )

  const filteredTrades = useMemo(() => {
    let filtered = [...normalizedTrades]
    if (filterType !== 'all') {
      filtered = filtered.filter((t) => t.type === filterType)
    }
    return filtered.sort((a, b) => {
      if (sortBy === 'date') return new Date(b.date) - new Date(a.date)
      if (sortBy === 'profit') return b.profit - a.profit
      if (sortBy === 'duration') {
        return parseDurationToMinutes(b.duration) - parseDurationToMinutes(a.duration)
      }
      return 0
    })
  }, [filterType, sortBy, normalizedTrades])

  const closedTrades = normalizedTrades.filter((t) => t.status === 'CLOSED' || t.status === 'EXECUTED')
  const closedCount = closedTrades.length
  const totalProfit = closedTrades.reduce((sum, t) => sum + t.profit, 0)

  const stats = {
    totalTrades: normalizedTrades.length,
    winRate: closedCount > 0 
      ? ((closedTrades.filter((t) => t.profit > 0).length / closedCount) * 100).toFixed(1)
      : 0,
    totalProfit,
    avgProfit: closedCount > 0
      ? totalProfit / closedCount
      : 0,
  }

  const handleExportCSV = () => {
    if (filteredTrades.length === 0) {
      toast.info('No trade data available to export.')
      return
    }

    const headers = ['symbol', 'type', 'quantity', 'entryPrice', 'exitPrice', 'profit', 'profitPct', 'date', 'duration', 'status']
    const rows = filteredTrades.map((trade) => [
      trade.symbol,
      trade.type,
      trade.quantity,
      trade.entryPrice,
      trade.exitPrice,
      trade.profit,
      trade.profitPct,
      trade.date,
      trade.duration,
      trade.status,
    ])

    const csvBody = [headers.join(','), ...rows.map((row) => row.join(','))].join('\n')
    const blob = new Blob([csvBody], { type: 'text/csv;charset=utf-8;' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `trades-${new Date().toISOString().slice(0, 10)}.csv`
    link.click()
    URL.revokeObjectURL(url)

    toast.success(`Exported ${filteredTrades.length} trades to CSV.`)
  }

  const handleGenerateReport = async () => {
    try {
      const report = await apiService.getPerformanceReport('today')
      const reportTrades = report?.trades ?? stats.totalTrades
      const reportPL = report?.totalP_L ?? stats.totalProfit
      toast.success(`Report generated: ${reportTrades} trades, P/L IDR ${toNumber(reportPL).toLocaleString('id-ID')}`)
    } catch (err) {
      toast.warning('Backend report unavailable. Displaying current on-screen analytics only.')
    }
  }

  if (loading) {
    return (
      <div className="tradelogs-page">
        <h1>Trade Logs & Analytics</h1>
        <div style={{ display: 'flex', gap: '1rem', marginBottom: '2rem' }}>
          <CardSkeleton />
          <CardSkeleton />
          <CardSkeleton />
          <CardSkeleton />
        </div>
        <CardSkeleton />
      </div>
    )
  }

  if (error) {
    return (
      <div className="tradelogs-page">
        <h1>Trade Logs & Analytics</h1>
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
            onClick={loadTradeLogs}
          >
            Try Again
          </Button>
        </div>
      </div>
    )
  }

  if (normalizedTrades.length === 0) {
    return (
      <div className="tradelogs-page">
        <h1>Trade Logs & Analytics</h1>
        <div style={{
          textAlign: 'center',
          padding: '3rem',
          background: 'var(--card-bg)',
          borderRadius: '12px'
        }}>
          <p style={{ color: 'var(--text-secondary)', marginBottom: '1rem' }}>📊 No trades yet. Start trading to see your logs here.</p>
          <Button 
            variant="primary"
            onClick={loadTradeLogs}
          >
            Refresh
          </Button>
        </div>
      </div>
    )
  }

  return (
    <div className="tradelogs-page">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '2rem' }}>
        <h1>Trade Logs & Analytics</h1>
        <div style={{ display: 'flex', gap: '1rem' }}>
          <Button 
            variant="success" 
            icon={<span>📥</span>}
            onClick={handleExportCSV}
          >
            Export CSV
          </Button>
          <Button 
            variant="primary"
            icon={<span>📊</span>}
            onClick={handleGenerateReport}
          >
            Generate Report
          </Button>
          <Button 
            variant="secondary"
            icon={<span>🔄</span>}
            onClick={loadTradeLogs}
          >
            Refresh
          </Button>
        </div>
      </div>

      {/* Stats Overview */}
      <div className="stats-overview">
        <div className="stat-card">
          <div className="stat-label">Total Trades</div>
          <div className="stat-value">{stats.totalTrades}</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Win Rate</div>
          <div className="stat-value positive">{stats.winRate}%</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Total Profit</div>
          <div className="stat-value positive">IDR {(stats.totalProfit / 1000).toFixed(1)}K</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Avg Profit/Trade</div>
          <div className="stat-value positive">IDR {(stats.avgProfit / 1000).toFixed(1)}K</div>
        </div>
      </div>

      {/* Filters & Sorting */}
      <div className="controls">
        <div className="filter-group">
          <label>Filter by Type</label>
          <select value={filterType} onChange={(e) => setFilterType(e.target.value)}>
            <option value="all">All Trades</option>
            <option value="BUY">Buy Orders</option>
            <option value="SELL">Sell Orders</option>
          </select>
        </div>
        <div className="sort-group">
          <label>Sort by</label>
          <select value={sortBy} onChange={(e) => setSortBy(e.target.value)}>
            <option value="date">Recent First</option>
            <option value="profit">Most Profitable</option>
            <option value="duration">Duration</option>
          </select>
        </div>
      </div>

      {/* Trades Table */}
      <div className="trades-table-container">
        <table className="trades-table">
          <thead>
            <tr>
              <th>Symbol</th>
              <th>Type</th>
              <th>Qty</th>
              <th>Entry Price</th>
              <th>Exit Price</th>
              <th>Profit/Loss</th>
              <th>Return %</th>
              <th>Date</th>
              <th>Duration</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {filteredTrades.map((trade) => (
              <tr key={trade.id} className={`trade-row ${trade.profit > 0 ? 'profitable' : trade.profit < 0 ? 'loss' : 'neutral'}`}>
                <td className="symbol">{trade.symbol}</td>
                <td className={`type ${trade.type.toLowerCase()}`}>{trade.type}</td>
                <td>{trade.quantity}</td>
                <td>IDR {trade.entryPrice.toLocaleString('id-ID')}</td>
                <td>{trade.exitPrice > 0 ? `IDR ${trade.exitPrice.toLocaleString('id-ID')}` : '-'}</td>
                <td className="profit">
                  <span className={trade.profit > 0 ? 'positive' : trade.profit < 0 ? 'negative' : ''}>
                    {trade.profit > 0 ? '+' : ''}IDR {trade.profit.toLocaleString('id-ID')}
                  </span>
                </td>
                <td className="return">
                  <span className={trade.profitPct > 0 ? 'positive' : trade.profitPct < 0 ? 'negative' : ''}>
                    {trade.profitPct > 0 ? '+' : ''}
                    {trade.profitPct.toFixed(2)}%
                  </span>
                </td>
                <td className="date">{new Date(trade.date).toLocaleDateString('id-ID')} {new Date(trade.date).toLocaleTimeString('id-ID').slice(0, 5)}</td>
                <td className="duration">{trade.duration}</td>
                <td className="status">
                  <span className={`status-badge ${trade.status.toLowerCase()}`}>
                    {trade.status}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
