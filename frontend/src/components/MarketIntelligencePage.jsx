import React from 'react'
import { mockMarketSentiment, mockSectorHeatmap, mockTopSignals } from '../utils/mockData'
import '../styles/market.css'

export default function MarketIntelligencePage() {
  return (
    <div className="market-page">
      <h1>Market Intelligence</h1>

      {/* Sentiment Panel */}
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
