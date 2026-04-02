import React, { useState } from 'react'
import Button from './Button'
import toast from '../store/toastStore'
import ChartComponent from './ChartComponent'
import { mockMarketSentiment, mockSectorHeatmap, mockTopSignals } from '../utils/mockData'
import '../styles/market.css'

const IDX_SYMBOLS = ['BBCA.JK', 'USIM.JK', 'KLBF.JK', 'ASII.JK', 'UNVR.JK', 'INDF.JK', 'PGAS.JK', 'GGRM.JK']
const TIMEFRAMES = ['1m', '5m', '15m', '30m', '1h', '4h', '1d', '1w']

export default function MarketIntelligencePage() {
  const [selectedSymbol, setSelectedSymbol] = useState('BBCA.JK')
  const [selectedTimeframe, setSelectedTimeframe] = useState('1d')
  return (
    <div className="market-page">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '2rem' }}>
        <h1>Market Intelligence</h1>
        <div style={{ display: 'flex', gap: '1rem' }}>
          <Button 
            variant="primary" 
            icon={<span>🔄</span>}
            size="md"
            onClick={() => toast.success('Market data refreshed!')}
          >
            Refresh Data
          </Button>
          <Button 
            variant="secondary"
            icon={<span>📊</span>}
            onClick={() => toast.info('Export feature coming soon')}
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
            <div className="timeframe-buttons" style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
              {TIMEFRAMES.map((tf) => (
                <Button
                  key={tf}
                  variant={selectedTimeframe === tf ? 'primary' : 'ghost'}
                  size="sm"
                  onClick={() => {
                    setSelectedTimeframe(tf)
                    toast.info(`Timeframe changed to ${tf}`)
                  }}
                >
                  {tf}
                </Button>
              ))}
            </div>
          </div>
        </div>

        {/* Live Chart */}
        <div className="chart-container">
          <ChartComponent symbol={selectedSymbol} timeframe={selectedTimeframe} theme="dark" />
        </div>
      </div>
      <div className="market-card sentiment-card">
        <h2>📊 Market Sentiment</h2>
        <div className="sentiment-container">
          <div className="sentiment-score">
            <div className="score-value">{mockMarketSentiment.score}/100</div>
            <div className="score-label">{mockMarketSentiment.sentiment}</div>
          </div>
          <div className="sentiment-breakdown">
            <div className="breakdown-item">
              <span>News Analysis</span>
              <div className="progress-bar">
                <div className="progress-fill" style={{ width: `${mockMarketSentiment.sourceBreakdown.newsAnalysis * 100}%` }}></div>
              </div>
              <span>{(mockMarketSentiment.sourceBreakdown.newsAnalysis * 100).toFixed(0)}%</span>
            </div>
            <div className="breakdown-item">
              <span>Technical</span>
              <div className="progress-bar">
                <div className="progress-fill neutral" style={{ width: `${mockMarketSentiment.sourceBreakdown.technicalAnalysis * 100}%` }}></div>
              </div>
              <span>{(mockMarketSentiment.sourceBreakdown.technicalAnalysis * 100).toFixed(0)}%</span>
            </div>
            <div className="breakdown-item">
              <span>Institutional Flow</span>
              <div className="progress-bar">
                <div className="progress-fill bearish" style={{ width: `${mockMarketSentiment.sourceBreakdown.institutionalFlow * 100}%` }}></div>
              </div>
              <span>{(mockMarketSentiment.sourceBreakdown.institutionalFlow * 100).toFixed(0)}%</span>
            </div>
          </div>
        </div>

        {/* News Feed */}
        <div className="news-feed">
          <h3>Recent Market News</h3>
          {mockMarketSentiment.recentNews && mockMarketSentiment.recentNews.map((item, idx) => (
            <div key={idx} className="news-item">
              <div className="news-time">{new Date(item.timestamp).toLocaleTimeString('id-ID')}</div>
              <div className="news-content">
                <div className="news-source">{item.source}</div>
                <div className="news-headline">{item.headline}</div>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Sector Heatmap */}
      <div className="market-card heatmap-card">
        <h2>🔥 Sector Performance Heatmap</h2>
        <div className="heatmap-grid">
          {mockSectorHeatmap && mockSectorHeatmap.map((sector) => {
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
      </div>

      {/* Top Movers */}
      <div className="market-card movers-card">
        <h2>🚀 Top Movers Today</h2>
        <div className="movers-grid">
          <div className="movers-column gainers">
            <h3>Top Gainers</h3>
            <div className="mover-item">
              <div className="mover-symbol">INDF.JK</div>
              <div className="mover-change">+3.2%</div>
            </div>
            <div className="mover-item">
              <div className="mover-symbol">UNVR.JK</div>
              <div className="mover-change">+2.1%</div>
            </div>
            <div className="mover-item">
              <div className="mover-symbol">ANTM.JK</div>
              <div className="mover-change">+0.8%</div>
            </div>
          </div>
          <div className="movers-column losers">
            <h3>Top Losers</h3>
            <div className="mover-item">
              <div className="mover-symbol">ASII.JK</div>
              <div className="mover-change">-2.3%</div>
            </div>
            <div className="mover-item">
              <div className="mover-symbol">PGAS.JK</div>
              <div className="mover-change">-1.8%</div>
            </div>
            <div className="mover-item">
              <div className="mover-symbol">GGRM.JK</div>
              <div className="mover-change">-0.9%</div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
