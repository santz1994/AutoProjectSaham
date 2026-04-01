import React, { useState } from 'react'
import '../styles/strategies.css'

export default function StrategiesPage() {
  const [selectedStrategy, setSelectedStrategy] = useState(null)

  const strategies = [
    {
      id: 'conservative',
      name: 'Conservative',
      icon: '🛡️',
      desc: 'Low risk, steady returns',
      expectedReturn: '8-12% p.a.',
      sharpeRatio: 1.2,
      maxDrawdown: '5-8%',
      rules: [
        'Only enter on volume +30%',
        'Take profit at +2%',
        'Stop loss at -1%',
        'Max 2 active trades',
      ],
    },
    {
      id: 'moderate',
      name: 'Moderate',
      icon: '⚖️',
      desc: 'Balanced risk/reward',
      expectedReturn: '15-25% p.a.',
      sharpeRatio: 1.8,
      maxDrawdown: '10-15%',
      rules: [
        'Enter on RSI oversold + sentiment check',
        'Take profit at +3-5%',
        'Stop loss at -2%',
        'Max 4 active trades',
      ],
    },
    {
      id: 'aggressive',
      name: 'Aggressive',
      icon: '⚡',
      desc: 'High risk, high reward',
      expectedReturn: '30-50% p.a.',
      sharpeRatio: 2.1,
      maxDrawdown: '20-30%',
      rules: [
        'Momentum-based entry (volume + price action)',
        'Take profit at +5-10%',
        'Stop loss at -3%',
        'Max 6 active trades',
      ],
    },
  ]

  return (
    <div className="strategies-page">
      <h1>Strategy Builder</h1>

      <div className="strategies-grid">
        {strategies.map((strategy) => (
          <div
            key={strategy.id}
            className={`strategy-card ${selectedStrategy?.id === strategy.id ? 'selected' : ''}`}
            onClick={() => setSelectedStrategy(strategy)}
          >
            <div className="strategy-header">
              <div className="strategy-icon">{strategy.icon}</div>
              <div className="strategy-title">{strategy.name}</div>
            </div>
            <div className="strategy-desc">{strategy.desc}</div>

            <div className="strategy-metrics">
              <div className="metric">
                <span className="label">Expected Return</span>
                <span className="value">{strategy.expectedReturn}</span>
              </div>
              <div className="metric">
                <span className="label">Sharpe Ratio</span>
                <span className="value">{strategy.sharpeRatio}</span>
              </div>
              <div className="metric">
                <span className="label">Max Drawdown</span>
                <span className="value">{strategy.maxDrawdown}</span>
              </div>
            </div>

            <button className="strategy-btn">Deploy Strategy</button>
          </div>
        ))}
      </div>

      {selectedStrategy && (
        <div className="strategy-details">
          <h2>📋 {selectedStrategy.name} Strategy Rules</h2>
          <div className="rules-list">
            {selectedStrategy.rules.map((rule, idx) => (
              <div key={idx} className="rule-item">
                <span className="rule-number">{idx + 1}</span>
                <span className="rule-text">{rule}</span>
              </div>
            ))}
          </div>

          {/* Backtest Results */}
          <div className="backtest-section">
            <h3>📊 Backtest Results (2023-2025)</h3>
            <div className="backtest-stats">
              <div className="stat">
                <span>Total Return</span>
                <span className="value positive">+45.2%</span>
              </div>
              <div className="stat">
                <span>Win Rate</span>
                <span className="value">62%</span>
              </div>
              <div className="stat">
                <span>Winning Trades</span>
                <span className="value positive">124</span>
              </div>
              <div className="stat">
                <span>Losing Trades</span>
                <span className="value negative">76</span>
              </div>
              <div className="stat">
                <span>Profit Factor</span>
                <span className="value">1.8x</span>
              </div>
              <div className="stat">
                <span>Avg Trade Value</span>
                <span className="value positive">+2.4%</span>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
