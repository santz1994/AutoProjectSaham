import React, { useState, useMemo } from 'react'
import Button from './Button'
import toast from '../store/toastStore'
import '../styles/tradelogs.css'

export default function TradeLogsPage() {
  const [filterType, setFilterType] = useState('all')
  const [sortBy, setSortBy] = useState('date')

  const allTrades = [
    {
      id: 1,
      symbol: 'INDF.JK',
      type: 'BUY',
      quantity: 100,
      entryPrice: 3050,
      exitPrice: 3128,
      profit: 7800,
      profitPct: 2.56,
      date: '2026-04-01 14:32:15',
      duration: '2h 15m',
      status: 'CLOSED',
    },
    {
      id: 2,
      symbol: 'UNVR.JK',
      type: 'BUY',
      quantity: 50,
      entryPrice: 2890,
      exitPrice: 2945,
      profit: 2750,
      profitPct: 1.90,
      date: '2026-04-01 10:45:22',
      duration: '6h 42m',
      status: 'CLOSED',
    },
    {
      id: 3,
      symbol: 'BBCA.JK',
      type: 'SELL',
      quantity: 75,
      entryPrice: 4200,
      exitPrice: 4165,
      profit: 2625,
      profitPct: 0.83,
      date: '2026-03-31 16:20:08',
      duration: '18h 30m',
      status: 'CLOSED',
    },
    {
      id: 4,
      symbol: 'BMRI.JK',
      type: 'BUY',
      quantity: 200,
      entryPrice: 7800,
      exitPrice: 0,
      profit: 0,
      profitPct: 0,
      date: '2026-04-01 09:15:44',
      duration: '7h 20m',
      status: 'OPEN',
    },
    {
      id: 5,
      symbol: 'ASII.JK',
      type: 'BUY',
      quantity: 150,
      entryPrice: 5200,
      exitPrice: 5078,
      profit: -1830,
      profitPct: -2.35,
      date: '2026-03-30 13:55:33',
      duration: '5h 45m',
      status: 'CLOSED',
    },
    {
      id: 6,
      symbol: 'TLKM.JK',
      type: 'BUY',
      quantity: 300,
      entryPrice: 3850,
      exitPrice: 3920,
      profit: 21000,
      profitPct: 1.82,
      date: '2026-03-29 11:22:10',
      duration: '1d 8h',
      status: 'CLOSED',
    },
  ]

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
