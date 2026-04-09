import React, { useState, useEffect, useMemo } from 'react'
import Button from './Button'
import toast from '../store/toastStore'
import { CardSkeleton } from './LoadingSkeletons'
import ChartComponent from './ChartComponent'
import apiService from '../utils/apiService'
import { useTradingStore } from '../store/useTradingStore'
import '../styles/market.css'

const IDX_SYMBOLS = ['BBCA.JK', 'USIM.JK', 'KLBF.JK', 'ASII.JK', 'UNVR.JK', 'INDF.JK', 'PGAS.JK', 'GGRM.JK']
const ORDERBOOK_DEPTH = 8

const formatPrice = (value) => {
  const num = Number(value)
  if (!Number.isFinite(num)) return '-'
  return num.toLocaleString('id-ID', {
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  })
}

const formatVolume = (value) => {
  const num = Number(value)
  if (!Number.isFinite(num)) return '-'
  return num.toLocaleString('id-ID', {
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  })
}

export default function MarketIntelligencePage({ theme = 'dark' }) {
  const [selectedSymbol, setSelectedSymbol] = useState('BBCA.JK')
  const [selectedTimeframe, setSelectedTimeframe] = useState('1d')
  const [marketSentiment, setMarketSentiment] = useState(null)
  const [sectorHeatmap, setSectorHeatmap] = useState([])
  const [topMovers, setTopMovers] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [orderType, setOrderType] = useState('limit')
  const [orderQty, setOrderQty] = useState(1)
  const [orderPrice, setOrderPrice] = useState('')
  const [submittingOrder, setSubmittingOrder] = useState(false)
  const [selectedSide, setSelectedSide] = useState('buy')
  const orderBook = useTradingStore((s) => s.orderBook)

  const normalizedBids = useMemo(() => (
    Array.isArray(orderBook?.bids)
      ? orderBook.bids
          .map((item) => ({
            price: Number(item?.price),
            volume: Number(item?.volume),
          }))
          .filter((item) => Number.isFinite(item.price) && item.price > 0 && Number.isFinite(item.volume) && item.volume > 0)
          .sort((left, right) => right.price - left.price)
          .slice(0, ORDERBOOK_DEPTH)
      : []
  ), [orderBook?.bids])

  const normalizedAsks = useMemo(() => (
    Array.isArray(orderBook?.asks)
      ? orderBook.asks
          .map((item) => ({
            price: Number(item?.price),
            volume: Number(item?.volume),
          }))
          .filter((item) => Number.isFinite(item.price) && item.price > 0 && Number.isFinite(item.volume) && item.volume > 0)
          .sort((left, right) => left.price - right.price)
          .slice(0, ORDERBOOK_DEPTH)
      : []
  ), [orderBook?.asks])

  const bestBid = normalizedBids.length > 0 ? normalizedBids[0].price : null
  const bestAsk = normalizedAsks.length > 0 ? normalizedAsks[0].price : null
  const spreadValue = (bestBid !== null && bestAsk !== null) ? (bestAsk - bestBid) : null
  const spreadPercent = (spreadValue !== null && bestAsk > 0)
    ? (spreadValue / bestAsk) * 100
    : null

  const handleSelectPriceLevel = (side, price) => {
    setSelectedSide(side)
    setOrderPrice(String(Number(price) || ''))
    setOrderType('limit')
  }

  const handleSubmitOrder = async (sideOverride = null) => {
    const side = String(sideOverride || selectedSide || 'buy').toLowerCase()
    const qty = Math.max(1, Number(orderQty) || 1)

    const payload = {
      symbol: selectedSymbol,
      side,
      qty,
      orderType,
    }

    const parsedPrice = Number(orderPrice)
    if (orderType === 'limit') {
      if (!Number.isFinite(parsedPrice) || parsedPrice <= 0) {
        toast.error('Limit price is required for limit order.')
        return
      }
      payload.limitPrice = parsedPrice
    } else {
      const marketRefPrice = Number.isFinite(parsedPrice) && parsedPrice > 0
        ? parsedPrice
        : (side === 'buy' ? bestAsk : bestBid)

      if (!Number.isFinite(marketRefPrice) || marketRefPrice <= 0) {
        toast.error('Market reference price is unavailable. Select a price level first.')
        return
      }
      payload.marketPrice = marketRefPrice
    }

    setSubmittingOrder(true)
    try {
      const response = await apiService.submitExecutionOrder(payload)
      const orderRef = response?.submission?.order_id || response?.submission?.id || '-'
      toast.success(`Order submitted (${side.toUpperCase()} x${qty}) • Ref: ${orderRef}`)
    } catch (err) {
      toast.error(`Order submission failed: ${err.message || 'Unknown error'}`)
    } finally {
      setSubmittingOrder(false)
    }
  }

  const loadMarketData = async () => {
    setLoading(true)
    setError(null)
    try {
      const [sentiment, heatmap, movers] = await Promise.all([
        apiService.getMarketSentiment(),
        apiService.getSectorHeatmap(),
        apiService.getTopMovers(),
      ])
      setMarketSentiment(sentiment)
      setSectorHeatmap(heatmap)
      setTopMovers(movers)
    } catch (err) {
      const errorMsg = err.message || 'Failed to load market data'
      setError(errorMsg)
      toast.error(errorMsg)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadMarketData()
  }, [])

  const handleRefresh = async () => {
    await loadMarketData()
  }

  const handleExportReport = () => {
    const report = {
      generatedAt: new Date().toISOString(),
      symbol: selectedSymbol,
      timeframe: selectedTimeframe,
      marketSentiment,
      sectorHeatmap,
      topMovers,
    }

    const blob = new Blob([JSON.stringify(report, null, 2)], {
      type: 'application/json;charset=utf-8',
    })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `market-report-${new Date().toISOString().slice(0, 10)}.json`
    link.click()
    URL.revokeObjectURL(url)

    toast.success('Market report exported successfully')
  }

  if (loading) {
    return (
      <div className="market-page">
        <h1>Market Intelligence</h1>
        <div style={{ display: 'flex', gap: '1rem', marginBottom: '2rem' }}>
          <CardSkeleton />
          <CardSkeleton />
        </div>
        <CardSkeleton />
        <CardSkeleton />
      </div>
    )
  }

  if (error) {
    return (
      <div className="market-page">
        <h1>Market Intelligence</h1>
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
            onClick={handleRefresh}
          >
            Try Again
          </Button>
        </div>
      </div>
    )
  }

  return (
    <div className="market-page">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '2rem' }}>
        <h1>Market Intelligence</h1>
        <div style={{ display: 'flex', gap: '1rem' }}>
          <Button 
            variant="primary" 
            icon={<span>🔄</span>}
            size="md"
            onClick={handleRefresh}
          >
            Refresh Data
          </Button>
          <Button 
            variant="secondary"
            icon={<span>📊</span>}
            onClick={handleExportReport}
          >
            Export Report
          </Button>
        </div>
      </div>

      {/* Real-Time Stock Chart */}
      <div className="market-card chart-card">
        <h2>📈 Real-Time Stock Chart</h2>
        
        {/* Chart Controls */}
        <div className="chart-controls">
          <div className="control-group">
            <label>Symbol</label>
            <select value={selectedSymbol} onChange={(e) => setSelectedSymbol(e.target.value)} className="control-select">
              {IDX_SYMBOLS.map((symbol) => (
                <option key={symbol} value={symbol}>
                  {symbol}
                </option>
              ))}
            </select>
          </div>
          
          <div className="control-group">
            <label>Timeframe</label>
            <div style={{ color: 'var(--text-secondary)', fontSize: '0.9rem' }}>
              Use chart toolbar to switch timeframe quickly.
            </div>
          </div>
        </div>

        {/* Live Chart */}
        <div className="chart-container">
          <ChartComponent
            symbol={selectedSymbol}
            timeframe={selectedTimeframe}
            onTimeframeChange={setSelectedTimeframe}
            theme={theme}
          />
        </div>
      </div>

      <div className="market-card orderbook-card">
        <h2>📚 Live Order Book (Ask/Bid)</h2>
        <div className="orderbook-summary">
          <div className="summary-pill">
            <span>Best Bid</span>
            <strong>{bestBid !== null ? formatPrice(bestBid) : '-'}</strong>
          </div>
          <div className="summary-pill">
            <span>Best Ask</span>
            <strong>{bestAsk !== null ? formatPrice(bestAsk) : '-'}</strong>
          </div>
          <div className={`summary-pill ${spreadValue !== null && spreadValue <= 0 ? 'tight' : 'wide'}`}>
            <span>Spread</span>
            <strong>
              {spreadValue !== null
                ? `${formatPrice(spreadValue)} (${(spreadPercent || 0).toFixed(2)}%)`
                : '-'}
            </strong>
          </div>
        </div>

        <div className="orderbook-grid">
          <div className="orderbook-table-wrapper asks">
            <h3>Ask (Sell Queue)</h3>
            <table className="orderbook-table">
              <thead>
                <tr>
                  <th>Price</th>
                  <th>Volume</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                {normalizedAsks.length === 0 ? (
                  <tr>
                    <td colSpan={3} className="orderbook-empty">No ask levels yet</td>
                  </tr>
                ) : (
                  normalizedAsks.map((level, idx) => (
                    <tr key={`ask-${idx}`} className={idx === 0 ? 'best-level' : ''}>
                      <td>{formatPrice(level.price)}</td>
                      <td>{formatVolume(level.volume)}</td>
                      <td>
                        <button
                          className="orderbook-action buy"
                          onClick={() => handleSelectPriceLevel('buy', level.price)}
                        >
                          Buy @ Ask
                        </button>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>

          <div className="orderbook-table-wrapper bids">
            <h3>Bid (Buy Queue)</h3>
            <table className="orderbook-table">
              <thead>
                <tr>
                  <th>Price</th>
                  <th>Volume</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                {normalizedBids.length === 0 ? (
                  <tr>
                    <td colSpan={3} className="orderbook-empty">No bid levels yet</td>
                  </tr>
                ) : (
                  normalizedBids.map((level, idx) => (
                    <tr key={`bid-${idx}`} className={idx === 0 ? 'best-level' : ''}>
                      <td>{formatPrice(level.price)}</td>
                      <td>{formatVolume(level.volume)}</td>
                      <td>
                        <button
                          className="orderbook-action sell"
                          onClick={() => handleSelectPriceLevel('sell', level.price)}
                        >
                          Sell @ Bid
                        </button>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>

        <div className="order-ticket">
          <h3>Quick Order Ticket</h3>
          <div className="ticket-grid">
            <label>
              Side
              <select value={selectedSide} onChange={(e) => setSelectedSide(e.target.value)}>
                <option value="buy">BUY</option>
                <option value="sell">SELL</option>
              </select>
            </label>
            <label>
              Type
              <select value={orderType} onChange={(e) => setOrderType(e.target.value)}>
                <option value="limit">Limit</option>
                <option value="market">Market</option>
              </select>
            </label>
            <label>
              Qty
              <input
                type="number"
                min="1"
                value={orderQty}
                onChange={(e) => setOrderQty(Math.max(1, parseInt(e.target.value || '1', 10)))}
              />
            </label>
            <label>
              {orderType === 'limit' ? 'Limit Price' : 'Reference Price'}
              <input
                type="number"
                min="1"
                value={orderPrice}
                onChange={(e) => setOrderPrice(e.target.value)}
                placeholder={orderType === 'limit' ? 'Set limit price' : 'Optional override'}
              />
            </label>
          </div>
          <div className="ticket-actions">
            <Button
              variant="primary"
              onClick={() => handleSubmitOrder('buy')}
              disabled={submittingOrder}
            >
              {submittingOrder ? 'Submitting...' : 'Submit BUY'}
            </Button>
            <Button
              variant="secondary"
              onClick={() => handleSubmitOrder('sell')}
              disabled={submittingOrder}
            >
              {submittingOrder ? 'Submitting...' : 'Submit SELL'}
            </Button>
          </div>
          <p className="order-ticket-note">
            Tip: click any ask/bid row action to auto-fill side and price.
          </p>
        </div>
      </div>

      {/* Market Sentiment */}
      <div className="market-card sentiment-card">
        <h2>📊 Market Sentiment</h2>
        {marketSentiment && (
          <>
            <div className="sentiment-container">
              <div className="sentiment-score">
                <div className="score-value">{marketSentiment.score}/100</div>
                <div className="score-label">{marketSentiment.sentiment}</div>
              </div>
              <div className="sentiment-breakdown">
                <div className="breakdown-item">
                  <span>News Analysis</span>
                  <div className="progress-bar">
                    <div className="progress-fill" style={{ width: `${marketSentiment.sourceBreakdown.newsAnalysis * 100}%` }}></div>
                  </div>
                  <span>{(marketSentiment.sourceBreakdown.newsAnalysis * 100).toFixed(0)}%</span>
                </div>
                <div className="breakdown-item">
                  <span>Technical</span>
                  <div className="progress-bar">
                    <div className="progress-fill neutral" style={{ width: `${marketSentiment.sourceBreakdown.technicalAnalysis * 100}%` }}></div>
                  </div>
                  <span>{(marketSentiment.sourceBreakdown.technicalAnalysis * 100).toFixed(0)}%</span>
                </div>
                <div className="breakdown-item">
                  <span>Institutional Flow</span>
                  <div className="progress-bar">
                    <div className="progress-fill bearish" style={{ width: `${marketSentiment.sourceBreakdown.institutionalFlow * 100}%` }}></div>
                  </div>
                  <span>{(marketSentiment.sourceBreakdown.institutionalFlow * 100).toFixed(0)}%</span>
                </div>
              </div>
            </div>

            {/* News Feed */}
            <div className="news-feed">
              <h3>Recent Market News</h3>
              {marketSentiment.recentNews && marketSentiment.recentNews.length > 0 ? (
                marketSentiment.recentNews.map((item, idx) => (
                  <div key={idx} className="news-item">
                    <div className="news-time">{new Date(item.timestamp).toLocaleTimeString('id-ID')}</div>
                    <div className="news-content">
                      <div className="news-source">{item.source}</div>
                      <div className="news-headline">{item.headline}</div>
                    </div>
                  </div>
                ))
              ) : (
                <p style={{ color: 'var(--text-secondary)' }}>No recent news available</p>
              )}
            </div>
          </>
        )}
      </div>

      {/* Sector Heatmap */}
      <div className="market-card heatmap-card">
        <h2>🔥 Sector Performance Heatmap</h2>
        {sectorHeatmap && sectorHeatmap.length > 0 ? (
          <div className="heatmap-grid">
            {sectorHeatmap.map((sector) => {
              const perfClass = sector.value > 5 ? 'bullish' : sector.value < -2 ? 'bearish' : 'neutral'
              return (
                <div
                  key={sector.name}
                  className={`heatmap-tile ${perfClass}`}
                  title={`${sector.name}: ${sector.value > 0 ? '+' : ''}${sector.value}%`}
                >
                  <div className="tile-name">{sector.name}</div>
                  <div className="tile-perf">{sector.value > 0 ? '📈' : '📉'} {Math.abs(sector.value).toFixed(1)}%</div>
                </div>
              )
            })}
          </div>
        ) : (
          <p style={{ color: 'var(--text-secondary)', padding: '2rem', textAlign: 'center' }}>No sector data available</p>
        )}
      </div>

      {/* Top Movers */}
      <div className="market-card movers-card">
        <h2>🚀 Top Movers Today</h2>
        {topMovers && (
          <div className="movers-grid">
            <div className="movers-column gainers">
              <h3>Top Gainers</h3>
              {topMovers.gainers && topMovers.gainers.length > 0 ? (
                topMovers.gainers.map((mover, idx) => (
                  <div key={idx} className="mover-item">
                    <div className="mover-symbol">{mover.symbol}</div>
                    <div className="mover-change">+{mover.change.toFixed(2)}%</div>
                  </div>
                ))
              ) : (
                <p style={{ color: '#999', fontSize: '0.9rem' }}>No gainers data</p>
              )}
            </div>
            <div className="movers-column losers">
              <h3>Top Losers</h3>
              {topMovers.losers && topMovers.losers.length > 0 ? (
                topMovers.losers.map((mover, idx) => (
                  <div key={idx} className="mover-item">
                    <div className="mover-symbol">{mover.symbol}</div>
                    <div className="mover-change">{mover.change.toFixed(2)}%</div>
                  </div>
                ))
              ) : (
                <p style={{ color: '#999', fontSize: '0.9rem' }}>No losers data</p>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
