import React, { useState, useMemo, useEffect } from 'react'
import Button from './Button'
import StatsCard from './StatsCard'
import AdvancedFilter from './AdvancedFilter'
import ExportMenu from './ExportMenu'
import toast from '../store/toastStore'
import { CardSkeleton } from './LoadingSkeletons'
import apiService from '../utils/apiService'
import '../styles/tradelogs.css'

export default function TradeLogsPageEnhanced() {
  const [trades, setTrades] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  
  // Filters
  const [filterType, setFilterType] = useState('all')
  const [sortBy, setSortBy] = useState('timestamp')
  const [sortOrder, setSortOrder] = useState('desc')
  const [searchQuery, setSearchQuery] = useState('')
  const [showFilters, setShowFilters] = useState(false)
  const [filters, setFilters] = useState({
    symbol: '',
    strategy: '',
    status: '',
    minProfit: '',
    maxProfit: ''
  })

  // Pagination
  const [currentPage, setCurrentPage] = useState(1)
  const [itemsPerPage] = useState(20)

  // Selected trades for bulk actions
  const [selectedTrades, setSelectedTrades] = useState(new Set())

  // Auto-refresh
  const [autoRefresh, setAutoRefresh] = useState(false)

  const loadTradeLogs = async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await apiService.getTradeLogs()
      setTrades(data)
      if (!autoRefresh) {
        toast.success(`Loaded ${data.length} trades`)
      }
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

  // Auto-refresh every 30 seconds
  useEffect(() => {
    if (!autoRefresh) return
    
    const interval = setInterval(loadTradeLogs, 30000)
    return () => clearInterval(interval)
  }, [autoRefresh])

  // Apply filters and search
  const filteredTrades = useMemo(() => {
    let filtered = trades

    // Type filter
    if (filterType !== 'all') {
      filtered = filtered.filter((t) => t.type === filterType)
    }

    // Search
    if (searchQuery) {
      const query = searchQuery.toLowerCase()
      filtered = filtered.filter(
        (t) =>
          t.symbol?.toLowerCase().includes(query) ||
          t.strategy?.toLowerCase().includes(query) ||
          t.status?.toLowerCase().includes(query)
      )
    }

    // Advanced filters
    if (filters.symbol) {
      filtered = filtered.filter((t) =>
        t.symbol?.toLowerCase().includes(filters.symbol.toLowerCase())
      )
    }
    if (filters.strategy) {
      filtered = filtered.filter((t) =>
        t.strategy?.toLowerCase().includes(filters.strategy.toLowerCase())
      )
    }
    if (filters.status) {
      filtered = filtered.filter((t) =>
        t.status?.toLowerCase() === filters.status.toLowerCase()
      )
    }
    if (filters.minProfit) {
      filtered = filtered.filter((t) => (t.price * t.quantity) >= parseFloat(filters.minProfit))
    }
    if (filters.maxProfit) {
      filtered = filtered.filter((t) => (t.price * t.quantity) <= parseFloat(filters.maxProfit))
    }

    // Sort
    return filtered.sort((a, b) => {
      let compareA, compareB

      switch (sortBy) {
        case 'timestamp':
          compareA = new Date(a.timestamp)
          compareB = new Date(b.timestamp)
          break
        case 'symbol':
          compareA = a.symbol
          compareB = b.symbol
          break
        case 'profit':
          compareA = a.price * a.quantity
          compareB = b.price * b.quantity
          break
        case 'quantity':
          compareA = a.quantity
          compareB = b.quantity
          break
        default:
          return 0
      }

      if (sortOrder === 'asc') {
        return compareA > compareB ? 1 : -1
      } else {
        return compareA < compareB ? 1 : -1
      }
    })
  }, [filterType, sortBy, sortOrder, searchQuery, filters, trades])

  // Pagination
  const paginatedTrades = useMemo(() => {
    const startIndex = (currentPage - 1) * itemsPerPage
    return filteredTrades.slice(startIndex, startIndex + itemsPerPage)
  }, [filteredTrades, currentPage, itemsPerPage])

  const totalPages = Math.ceil(filteredTrades.length / itemsPerPage)

  // Stats calculation
  const stats = useMemo(() => {
    const closedTrades = trades.filter((t) => t.status === 'EXECUTED' || t.status === 'CLOSED')
    const profitableTrades = closedTrades.filter((t) => t.type === 'SELL')
    const totalProfit = closedTrades.reduce((sum, t) => {
      const value = t.price * t.quantity
      return sum + (t.type === 'SELL' ? value : -value)
    }, 0)

    return {
      totalTrades: trades.length,
      activeTrades: trades.filter((t) => t.status === 'PENDING' || t.status === 'OPEN').length,
      winRate: closedTrades.length > 0
        ? ((profitableTrades.length / closedTrades.length) * 100).toFixed(1)
        : 0,
      totalProfit,
      avgTradeValue: trades.length > 0
        ? (trades.reduce((sum, t) => sum + t.price * t.quantity, 0) / trades.length)
        : 0,
    }
  }, [trades])

  const handleSort = (column) => {
    if (sortBy === column) {
      setSortOrder(sortOrder === 'asc' ? 'desc' : 'asc')
    } else {
      setSortBy(column)
      setSortOrder('desc')
    }
  }

  const handleSelectAll = () => {
    if (selectedTrades.size === paginatedTrades.length) {
      setSelectedTrades(new Set())
    } else {
      setSelectedTrades(new Set(paginatedTrades.map((t) => t.id)))
    }
  }

  const handleSelectTrade = (id) => {
    const newSelected = new Set(selectedTrades)
    if (newSelected.has(id)) {
      newSelected.delete(id)
    } else {
      newSelected.add(id)
    }
    setSelectedTrades(newSelected)
  }

  const handleExport = async (format) => {
    const selectedData = trades.filter((t) => selectedTrades.has(t.id))
    const dataToExport = selectedData.length > 0 ? selectedData : filteredTrades

    // Call API service for export
    try {
      if (format === 'csv' || format === 'excel') {
        await apiService.exportTrades(format)
      }
      toast.success(`Exported ${dataToExport.length} trades as ${format.toUpperCase()}`)
    } catch (error) {
      console.error('Export error:', error)
    }
  }

  if (loading && trades.length === 0) {
    return (
      <div className="tradelogs-page">
        <h1>📊 Trade Logs & Analytics</h1>
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

  return (
    <div className="tradelogs-page">
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '2rem' }}>
        <h1>📊 Trade Logs & Analytics</h1>
        <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center' }}>
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
            onClick={loadTradeLogs}
            loading={loading}
          >
            Refresh
          </Button>
          <ExportMenu
            data={filteredTrades}
            filename="trade_logs"
            onExport={handleExport}
          />
        </div>
      </div>

      {/* Stats Cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '1rem', marginBottom: '2rem' }}>
        <StatsCard
          icon="📈"
          title="Total Trades"
          value={stats.totalTrades}
          subtitle={`${stats.activeTrades} active`}
        />
        <StatsCard
          icon="🎯"
          title="Win Rate"
          value={`${stats.winRate}%`}
          trend={parseFloat(stats.winRate) >= 60 ? 'up' : parseFloat(stats.winRate) >= 40 ? 'neutral' : 'down'}
        />
        <StatsCard
          icon="💰"
          title="Total P&L"
          value={`IDR ${(stats.totalProfit / 1000).toFixed(1)}K`}
          trend={stats.totalProfit > 0 ? 'up' : stats.totalProfit < 0 ? 'down' : 'neutral'}
          change={stats.totalProfit > 0 ? `+${stats.totalProfit.toFixed(0)}` : stats.totalProfit.toFixed(0)}
        />
        <StatsCard
          icon="📊"
          title="Avg Trade Value"
          value={`IDR ${(stats.avgTradeValue / 1000).toFixed(1)}K`}
        />
      </div>

      {/* Search and Filters */}
      <div style={{ marginBottom: '1.5rem' }}>
        <div style={{ display: 'flex', gap: '1rem', marginBottom: '1rem', flexWrap: 'wrap' }}>
          <input
            type="text"
            placeholder="🔍 Search symbol, strategy, status..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            style={{
              flex: '1',
              minWidth: '250px',
              padding: '0.75rem 1rem',
              background: 'rgba(148, 163, 184, 0.1)',
              border: '1px solid #475569',
              borderRadius: '8px',
              color: '#f1f5f9',
              fontSize: '0.9375rem',
            }}
          />
          
          <select
            value={filterType}
            onChange={(e) => setFilterType(e.target.value)}
            style={{
              padding: '0.75rem 1rem',
              background: 'rgba(148, 163, 184, 0.1)',
              border: '1px solid #475569',
              borderRadius: '8px',
              color: '#f1f5f9',
              fontSize: '0.9375rem',
            }}
          >
            <option value="all">All Types</option>
            <option value="BUY">Buy Only</option>
            <option value="SELL">Sell Only</option>
          </select>
        </div>

        <AdvancedFilter
          filters={filters}
          onApply={setFilters}
          onReset={() => setFilters({ symbol: '', strategy: '', status: '', minProfit: '', maxProfit: '' })}
          isOpen={showFilters}
          onToggle={() => setShowFilters(!showFilters)}
        />
      </div>

      {/* Trades Table */}
      {filteredTrades.length === 0 ? (
        <div style={{ textAlign: 'center', padding: '3rem', background: '#1a1a1a', borderRadius: '12px' }}>
          <p style={{ color: '#94a3b8', fontSize: '1.125rem' }}>📭 No trades found</p>
          <p style={{ color: '#64748b', fontSize: '0.875rem', marginTop: '0.5rem' }}>
            {searchQuery || Object.values(filters).some(Boolean) ? 'Try adjusting your filters' : 'Trades will appear here once bot starts trading'}
          </p>
        </div>
      ) : (
        <>
          <div className="trades-table-container">
            <table className="trades-table">
              <thead>
                <tr>
                  <th style={{ width: '40px' }}>
                    <input
                      type="checkbox"
                      checked={selectedTrades.size === paginatedTrades.length && paginatedTrades.length > 0}
                      onChange={handleSelectAll}
                    />
                  </th>
                  <th onClick={() => handleSort('timestamp')} style={{ cursor: 'pointer' }}>
                    Date/Time {sortBy === 'timestamp' && (sortOrder === 'asc' ? '↑' : '↓')}
                  </th>
                  <th onClick={() => handleSort('symbol')} style={{ cursor: 'pointer' }}>
                    Symbol {sortBy === 'symbol' && (sortOrder === 'asc' ? '↑' : '↓')}
                  </th>
                  <th>Type</th>
                  <th onClick={() => handleSort('quantity')} style={{ cursor: 'pointer' }}>
                    Quantity {sortBy === 'quantity' && (sortOrder === 'asc' ? '↑' : '↓')}
                  </th>
                  <th>Price</th>
                  <th onClick={() => handleSort('profit')} style={{ cursor: 'pointer' }}>
                    Total {sortBy === 'profit' && (sortOrder === 'asc' ? '↑' : '↓')}
                  </th>
                  <th>Status</th>
                  <th>Strategy</th>
                  <th>Signal</th>
                </tr>
              </thead>
              <tbody>
                {paginatedTrades.map((trade) => (
                  <tr key={trade.id} className={selectedTrades.has(trade.id) ? 'selected' : ''}>
                    <td>
                      <input
                        type="checkbox"
                        checked={selectedTrades.has(trade.id)}
                        onChange={() => handleSelectTrade(trade.id)}
                      />
                    </td>
                    <td>{new Date(trade.timestamp).toLocaleString('id-ID')}</td>
                    <td className="symbol-cell">{trade.symbol}</td>
                    <td>
                      <span className={`type-badge ${trade.type.toLowerCase()}`}>
                        {trade.type === 'BUY' ? '📈' : '📉'} {trade.type}
                      </span>
                    </td>
                    <td>{trade.quantity.toLocaleString()}</td>
                    <td>IDR {trade.price.toLocaleString()}</td>
                    <td className={trade.type === 'SELL' ? 'profit-positive' : 'profit-negative'}>
                      IDR {(trade.price * trade.quantity).toLocaleString()}
                    </td>
                    <td>
                      <span className={`status-badge ${trade.status.toLowerCase()}`}>
                        {trade.status}
                      </span>
                    </td>
                    <td>{trade.strategy}</td>
                    <td style={{ fontSize: '0.8125rem', color: '#94a3b8' }}>{trade.signal || '-'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Pagination */}
          {totalPages > 1 && (
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '1.5rem' }}>
              <div style={{ color: '#94a3b8', fontSize: '0.875rem' }}>
                Showing {((currentPage - 1) * itemsPerPage) + 1} to {Math.min(currentPage * itemsPerPage, filteredTrades.length)} of {filteredTrades.length} trades
              </div>
              <div style={{ display: 'flex', gap: '0.5rem' }}>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => setCurrentPage(Math.max(1, currentPage - 1))}
                  disabled={currentPage === 1}
                >
                  ← Previous
                </Button>
                <div style={{ display: 'flex', gap: '0.25rem' }}>
                  {Array.from({ length: Math.min(5, totalPages) }, (_, i) => {
                    const page = i + 1
                    return (
                      <button
                        key={page}
                        onClick={() => setCurrentPage(page)}
                        style={{
                          padding: '0.5rem 0.75rem',
                          background: currentPage === page ? '#3b82f6' : 'transparent',
                          border: '1px solid #475569',
                          borderRadius: '6px',
                          color: '#f1f5f9',
                          cursor: 'pointer',
                          fontSize: '0.875rem',
                        }}
                      >
                        {page}
                      </button>
                    )
                  })}
                </div>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => setCurrentPage(Math.min(totalPages, currentPage + 1))}
                  disabled={currentPage === totalPages}
                >
                  Next →
                </Button>
              </div>
            </div>
          )}
        </>
      )}

      {/* Bulk Actions */}
      {selectedTrades.size > 0 && (
        <div style={{
          position: 'fixed',
          bottom: '2rem',
          left: '50%',
          transform: 'translateX(-50%)',
          background: 'linear-gradient(135deg, #1e293b 0%, #0f172a 100%)',
          border: '1px solid #3b82f6',
          borderRadius: '12px',
          padding: '1rem 1.5rem',
          boxShadow: '0 10px 40px rgba(0, 0, 0, 0.5)',
          display: 'flex',
          gap: '1rem',
          alignItems: 'center',
          zIndex: 100,
        }}>
          <span style={{ color: '#f1f5f9', fontSize: '0.9375rem' }}>
            {selectedTrades.size} trade{selectedTrades.size > 1 ? 's' : ''} selected
          </span>
          <Button
            variant="primary"
            size="sm"
            icon={<span>📥</span>}
            onClick={() => handleExport('csv')}
          >
            Export Selected
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setSelectedTrades(new Set())}
          >
            Clear Selection
          </Button>
        </div>
      )}
    </div>
  )
}
