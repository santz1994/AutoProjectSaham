import React, { useState, useMemo, useEffect } from 'react'
import Button from './Button'
import toast from '../store/toastStore'
import { CardSkeleton } from './LoadingSkeletons'
import apiService from '../utils/apiService'
import '../styles/tradelogs.css'

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
      setTrades(data)
      toast.success('Trade logs loaded successfully')
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

  const filteredTrades = useMemo(() => {
    let filtered = allTrades
    if (filterType !== 'all') {
      filtered = filtered.filter((t) => t.type === filterType)
    }
    return filtered.sort((a, b) => {
      if (sortBy === 'date') return new Date(b.date) - new Date(a.date)
      if (sortBy === 'profit') return b.profit - a.profit
      if (sortBy === 'duration') return Math.random() - 0.5 // pseudo-sort for demo
      return 0
    })
  }, [filterType, sortBy])

  const stats = {
    totalTrades: allTrades.length,
    winRate: ((allTrades.filter((t) => t.profit > 0).length / allTrades.filter((t) => t.status === 'CLOSED').length) * 100).toFixed(1),
    totalProfit: allTrades.reduce((sum, t) => sum + t.profit, 0),
    avgProfit: (allTrades.reduce((sum, t) => sum + t.profit, 0) / allTrades.filter((t) => t.status === 'CLOSED').length).toFixed(2),
  }

  return (
    <div className="tradelogs-page">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '2rem' }}>
        <h1>Trade Logs & Analytics</h1>
        <div style={{ display: 'flex', gap: '1rem' }}>
          <Button 
            variant="success" 
            icon={<span>📥</span>}
            onClick={() => toast.success('Trades exported to CSV!')}
          >
            Export CSV
          </Button>
          <Button 
            variant="primary"
            icon={<span>📊</span>}
            onClick={() => toast.info('Analytics report generated')}
          >
            Generate Report
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
