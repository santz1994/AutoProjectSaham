/**
 * Risk Analytics Dashboard Component (Phase 8.2)
 * Shows return distribution histogram, drawdown chart, and risk metrics
 */

import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { toast } from '../store/toastStore';
import apiService from '../utils/apiService';

const RISK_METRICS = [
  { key: 'sharpeRatio', label: 'Sharpe Ratio', icon: '📈', threshold: { good: 1.5, warn: 0.5 } },
  { key: 'maxDrawdown', label: 'Max Drawdown', icon: '📉', threshold: { good: -0.1, warn: -0.25 }, format: 'percent' },
  { key: 'sortinoRatio', label: 'Sortino Ratio', icon: '🎯', threshold: { good: 2.0, warn: 1.0 } },
  { key: 'calmarRatio', label: 'Calmar Ratio', icon: '⚖️', threshold: { good: 1.0, warn: 0.5 } },
  { key: 'winRate', label: 'Win Rate', icon: '🏆', threshold: { good: 0.6, warn: 0.5 }, format: 'percent' },
  { key: 'profitFactor', label: 'Profit Factor', icon: '💰', threshold: { good: 1.5, warn: 1.0 } },
  { key: 'avgWin', label: 'Avg Win', icon: '✅', format: 'currency' },
  { key: 'avgLoss', label: 'Avg Loss', icon: '❌', format: 'currency' },
  { key: 'totalTrades', label: 'Total Trades', icon: '📊' },
  { key: 'consecutiveWins', label: 'Max Consec. Wins', icon: '🔥' },
  { key: 'consecutiveLosses', label: 'Max Consec. Losses', icon: '🧊' },
  { key: 'avgHoldingTime', label: 'Avg Hold Time', icon: '⏱️', format: 'duration' },
];

function formatMetricValue(value, format) {
  if (value === undefined || value === null) return 'N/A';
  switch (format) {
    case 'percent': return `${(value * 100).toFixed(1)}%`;
    case 'currency': return `$${value.toFixed(2)}`;
    case 'duration': return `${value}min`;
    default: return typeof value === 'number' ? value.toFixed(2) : value;
  }
}

function getMetricStatus(key, value) {
  const metric = RISK_METRICS.find((m) => m.key === key);
  if (!metric?.threshold || value === undefined) return 'neutral';
  const { good, warn } = metric.threshold;
  // For drawdown, lower is better (more negative is worse)
  if (key === 'maxDrawdown') {
    if (value >= good) return 'good';
    if (value >= warn) return 'warn';
    return 'bad';
  }
  if (value >= good) return 'good';
  if (value >= warn) return 'warn';
  return 'bad';
}

function HistogramBar({ count, maxCount, binLabel, theme }) {
  const height = maxCount > 0 ? (count / maxCount) * 100 : 0;
  const isPositive = parseFloat(binLabel) >= 0;

  return (
    <div className="histogram-bar-wrapper" title={`${binLabel}%: ${count} trades`}>
      <div
        className={`histogram-bar ${isPositive ? 'positive' : 'negative'}`}
        style={{ height: `${Math.max(height, 2)}%` }}
      >
        {count > 0 && <span className="bar-count">{count}</span>}
      </div>
      <span className="histogram-label">{binLabel}</span>
    </div>
  );
}

function EquityCurveChart({ equity, theme }) {
  if (!equity || equity.length === 0) return null;

  const maxVal = Math.max(...equity);
  const minVal = Math.min(...equity);
  const range = maxVal - minVal || 1;
  const svgWidth = 600;
  const svgHeight = 200;
  const padding = 20;

  const points = equity.map((val, i) => {
    const x = padding + (i / (equity.length - 1)) * (svgWidth - 2 * padding);
    const y = svgHeight - padding - ((val - minVal) / range) * (svgHeight - 2 * padding);
    return `${x},${y}`;
  }).join(' ');

  const areaPoints = `${padding},${svgHeight - padding} ${points} ${svgWidth - padding},${svgHeight - padding}`;

  return (
    <svg viewBox={`0 0 ${svgWidth} ${svgHeight}`} className="equity-curve-svg">
      {/* Grid lines */}
      {[0.25, 0.5, 0.75].map((pct) => {
        const y = padding + pct * (svgHeight - 2 * padding);
        return (
          <line key={pct} x1={padding} y1={y} x2={svgWidth - padding} y2={y}
            stroke={theme === 'dark' ? '#333' : '#e5e7eb'} strokeDasharray="4,4" />
        );
      })}
      {/* Area fill */}
      <polygon points={areaPoints} fill="url(#equityGradient)" opacity="0.3" />
      {/* Line */}
      <polyline points={points} fill="none" stroke="#22c55e" strokeWidth="2" />
      {/* Gradient definition */}
      <defs>
        <linearGradient id="equityGradient" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#22c55e" stopOpacity="0.4" />
          <stop offset="100%" stopColor="#22c55e" stopOpacity="0" />
        </linearGradient>
      </defs>
      {/* Y-axis labels */}
      <text x={padding - 5} y={padding + 5} fill={theme === 'dark' ? '#888' : '#666'} fontSize="10" textAnchor="end">
        ${maxVal.toFixed(0)}
      </text>
      <text x={padding - 5} y={svgHeight - padding} fill={theme === 'dark' ? '#888' : '#666'} fontSize="10" textAnchor="end">
        ${minVal.toFixed(0)}
      </text>
    </svg>
  );
}

function DrawdownChart({ drawdowns, theme }) {
  if (!drawdowns || drawdowns.length === 0) return null;

  const maxDD = Math.min(...drawdowns);
  const svgWidth = 600;
  const svgHeight = 120;
  const padding = 20;

  const points = drawdowns.map((val, i) => {
    const x = padding + (i / (drawdowns.length - 1)) * (svgWidth - 2 * padding);
    const y = padding + (val / maxDD) * (svgHeight - 2 * padding);
    return `${x},${y}`;
  }).join(' ');

  const areaPoints = `${padding},${padding} ${points} ${svgWidth - padding},${padding}`;

  return (
    <svg viewBox={`0 0 ${svgWidth} ${svgHeight}`} className="drawdown-svg">
      <polygon points={areaPoints} fill="#ef4444" opacity="0.2" />
      <polyline points={points} fill="none" stroke="#ef4444" strokeWidth="1.5" />
      <text x={padding - 5} y={padding + 5} fill={theme === 'dark' ? '#888' : '#666'} fontSize="10" textAnchor="end">
        0%
      </text>
      <text x={padding - 5} y={svgHeight - padding} fill="#ef4444" fontSize="10" textAnchor="end">
        {(maxDD * 100).toFixed(1)}%
      </text>
    </svg>
  );
}

export default function RiskAnalytics({ theme = 'dark' }) {
  const [riskData, setRiskData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState('overview');

  const generateMockData = useCallback(() => {
    // Generate realistic mock returns
    const returns = Array.from({ length: 500 }, () => {
      const r = (Math.random() - 0.48) * 0.08;
      return parseFloat(r.toFixed(4));
    });

    // Build histogram bins
    const binCount = 30;
    const minReturn = Math.min(...returns);
    const maxReturn = Math.max(...returns);
    const binWidth = (maxReturn - minReturn) / binCount;
    const bins = Array.from({ length: binCount }, (_, i) => {
      const binStart = minReturn + i * binWidth;
      const binEnd = binStart + binWidth;
      const count = returns.filter((r) => r >= binStart && r < binEnd).length;
      return {
        label: ((binStart + binEnd) / 2 * 100).toFixed(1),
        count,
      };
    });

    // Build equity curve
    let equity = 10000;
    const equityCurve = [equity];
    returns.forEach((r) => {
      equity *= (1 + r);
      equityCurve.push(parseFloat(equity.toFixed(2)));
    });

    // Build drawdown curve
    let peak = equityCurve[0];
    const drawdowns = equityCurve.map((val) => {
      if (val > peak) peak = val;
      return (val - peak) / peak;
    });

    // Win/loss stats
    const wins = returns.filter((r) => r > 0);
    const losses = returns.filter((r) => r <= 0);

    // Max consecutive
    let maxConsecWins = 0, maxConsecLosses = 0, curWins = 0, curLosses = 0;
    returns.forEach((r) => {
      if (r > 0) { curWins++; curLosses = 0; maxConsecWins = Math.max(maxConsecWins, curWins); }
      else { curLosses++; curWins = 0; maxConsecLosses = Math.max(maxConsecLosses, curLosses); }
    });

    // Sharpe & Sortino
    const meanReturn = returns.reduce((a, b) => a + b, 0) / returns.length;
    const stdDev = Math.sqrt(returns.reduce((a, b) => a + (b - meanReturn) ** 2, 0) / returns.length);
    const downsideReturns = returns.filter((r) => r < 0);
    const downsideDev = Math.sqrt(downsideReturns.reduce((a, b) => a + b ** 2, 0) / downsideReturns.length);
    const annualFactor = Math.sqrt(365 * 24 * 12); // 5m candles annualized

    return {
      metrics: {
        sharpeRatio: parseFloat(((meanReturn / stdDev) * annualFactor).toFixed(2)),
        maxDrawdown: parseFloat(Math.min(...drawdowns).toFixed(4)),
        sortinoRatio: parseFloat(((meanReturn / downsideDev) * annualFactor).toFixed(2)),
        calmarRatio: parseFloat((meanReturn * annualFactor / Math.abs(Math.min(...drawdowns))).toFixed(2)),
        winRate: wins.length / returns.length,
        profitFactor: parseFloat((Math.abs(wins.reduce((a, b) => a + b, 0)) / Math.abs(losses.reduce((a, b) => a + b, 0))).toFixed(2)),
        avgWin: parseFloat((wins.reduce((a, b) => a + b, 0) / wins.length * 100).toFixed(4)),
        avgLoss: parseFloat((losses.reduce((a, b) => a + b, 0) / losses.length * 100).toFixed(4)),
        totalTrades: returns.length,
        consecutiveWins: maxConsecWins,
        consecutiveLosses: maxConsecLosses,
        avgHoldingTime: Math.floor(Math.random() * 30 + 5),
      },
      histogram: bins,
      equityCurve,
      drawdowns,
      returns,
    };
  }, []);

  useEffect(() => {
    const fetchData = async () => {
      setLoading(true);
      try {
        const response = await apiService.getRiskAnalytics?.();
        const hasArrays = Array.isArray(response?.returns)
          && Array.isArray(response?.histogram)
          && Array.isArray(response?.equityCurve)
          && Array.isArray(response?.drawdowns);
        if (response && response.metrics && hasArrays) {
          setRiskData(response);
        } else {
          setRiskData(generateMockData());
        }
      } catch {
        setRiskData(generateMockData());
      } finally {
        setLoading(false);
      }
    };
    fetchData();
  }, [generateMockData]);

  if (loading || !riskData) {
    return (
      <div className={`panel risk-analytics theme-${theme}`} data-theme={theme}>
        <div className="panel-header"><h3>📊 Risk Analytics</h3></div>
        <div className="risk-loading">Loading risk analytics...</div>
      </div>
    );
  }

  const { metrics, histogram, equityCurve, drawdowns } = riskData;
  const maxHistCount = histogram.length ? Math.max(...histogram.map((b) => b.count)) : 0;

  const tabs = [
    { key: 'overview', label: '📋 Overview' },
    { key: 'distribution', label: '📊 Returns Distribution' },
    { key: 'drawdown', label: '📉 Drawdown Analysis' },
  ];

  return (
    <div className={`panel risk-analytics theme-${theme}`} data-theme={theme}>
      <div className="panel-header">
        <h3>📊 Risk Analytics</h3>
        <div className="risk-tabs">
          {tabs.map((tab) => (
            <button
              key={tab.key}
              className={`risk-tab ${activeTab === tab.key ? 'active' : ''}`}
              onClick={() => setActiveTab(tab.key)}
            >
              {tab.label}
            </button>
          ))}
        </div>
      </div>

      {activeTab === 'overview' && (
        <>
          {/* Equity Curve */}
          <div className="risk-section">
            <h4>Equity Curve</h4>
            <EquityCurveChart equity={equityCurve} theme={theme} />
          </div>

          {/* Key Metrics Grid */}
          <div className="risk-metrics-grid">
            {RISK_METRICS.map(({ key, label, icon, format }) => {
              const value = metrics[key];
              const status = getMetricStatus(key, value);
              return (
                <div key={key} className={`risk-metric-card status-${status}`}>
                  <span className="metric-icon">{icon}</span>
                  <span className="metric-label">{label}</span>
                  <span className={`metric-value status-${status}`}>
                    {formatMetricValue(value, format)}
                  </span>
                </div>
              );
            })}
          </div>
        </>
      )}

      {activeTab === 'distribution' && (
        <div className="risk-section">
          <h4>Return Distribution ({riskData.returns?.length || 0} trades)</h4>
          <div className="histogram-container">
            {histogram.map((bin, i) => (
              <HistogramBar
                key={i}
                count={bin.count}
                maxCount={maxHistCount}
                binLabel={bin.label}
                theme={theme}
              />
            ))}
          </div>
          <div className="distribution-stats">
            {(() => {
              const returns = Array.isArray(riskData.returns) ? riskData.returns : [];
              const count = returns.length;
              const mean = count ? returns.reduce((a, b) => a + b, 0) / count : 0;
              const variance = count
                ? returns.reduce((a, b) => a + (b - mean) ** 2, 0) / count
                : 0;
              const std = Math.sqrt(variance);
              const skew = count && std > 0
                ? returns.reduce((a, b) => a + ((b - mean) / std) ** 3, 0) / count
                : 0;
              return (
                <>
                  <span>Mean: {(mean * 100).toFixed(3)}%</span>
                  <span>Std Dev: {(std * 100).toFixed(3)}%</span>
                  <span>Skew: {skew.toFixed(3)}</span>
                </>
              );
            })()}
          </div>
        </div>
      )}

      {activeTab === 'drawdown' && (
        <div className="risk-section">
          <h4>Drawdown Over Time</h4>
          <DrawdownChart drawdowns={drawdowns} theme={theme} />
          <div className="drawdown-stats">
            <span>Max Drawdown: {(metrics.maxDrawdown * 100).toFixed(2)}%</span>
            <span>Recovery Factor: {metrics.profitFactor}</span>
          </div>
        </div>
      )}
    </div>
  );
}