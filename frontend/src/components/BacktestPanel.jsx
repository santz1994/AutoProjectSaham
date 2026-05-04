/**
 * BacktestPanel.jsx – Frontend Backtesting (Phase 8.2)
 *
 * Allows users to run backtests against historical data with
 * configurable parameters. Displays equity curve, key metrics,
 * and trade-by-trade results.
 */

import React, { useState, useEffect, useCallback } from 'react';
import toast from '../store/toastStore';
import apiService from '../utils/apiService';

/* ─── helpers ─── */
const fmt = (n, dec = 2) => {
  if (n == null || isNaN(n)) return '—';
  return Number(n).toLocaleString('en-US', { minimumFractionDigits: dec, maximumFractionDigits: dec });
};

const fmtPct = (n) => {
  if (n == null || isNaN(n)) return '—';
  return `${n >= 0 ? '+' : ''}${Number(n).toFixed(2)}%`;
};

const pnlColor = (v) => (v >= 0 ? '#10b981' : '#ef4444');

/* ─── Equity Curve Canvas ─── */
function EquityCurveChart({ points = [] }) {
  if (points.length < 2) return null;
  const max = Math.max(...points);
  const min = Math.min(...points);
  const range = max - min || 1;
  const up = points[points.length - 1] >= points[0];

  return (
    <div className="bt-chart">
      <div className="bt-chart-labels">
        <span>${fmt(min)}</span>
        <span>${fmt(max)}</span>
      </div>
      <div className="bt-chart-bars">
        {points.map((v, i) => {
          const h = Math.max(2, ((v - min) / range) * 100);
          return (
            <div key={i} className="bt-bar-wrapper">
              <div
                className="bt-bar"
                style={{
                  height: `${h}%`,
                  background: up
                    ? `linear-gradient(to top, #10b98166, #10b981)`
                    : `linear-gradient(to top, #ef444466, #ef4444)`,
                }}
                title={`Step ${i + 1}: $${fmt(v)}`}
              />
            </div>
          );
        })}
      </div>
      <div className="bt-chart-x-label">Timesteps →</div>
    </div>
  );
}

/* ─── Trade Table ─── */
function TradeTable({ trades = [] }) {
  const [showAll, setShowAll] = useState(false);
  const visible = showAll ? trades : trades.slice(0, 20);

  if (!trades.length) return <div className="bt-empty">No trades recorded</div>;

  return (
    <>
      <div className="bt-table-wrap">
        <table className="bt-table">
          <thead>
            <tr>
              <th>#</th>
              <th>Time</th>
              <th>Side</th>
              <th>Symbol</th>
              <th>Entry</th>
              <th>Exit</th>
              <th>P&L</th>
              <th>Return</th>
            </tr>
          </thead>
          <tbody>
            {visible.map((t, i) => (
              <tr key={i}>
                <td>{i + 1}</td>
                <td className="bt-time">{t.timestamp || t.time || '—'}</td>
                <td>
                  <span className={`bt-badge ${t.side === 'buy' || t.side === 'long' ? 'bt-long' : 'bt-short'}`}>
                    {(t.side || 'hold').toUpperCase()}
                  </span>
                </td>
                <td className="bt-symbol">{t.symbol || '—'}</td>
                <td>${fmt(t.entry_price)}</td>
                <td>${fmt(t.exit_price)}</td>
                <td style={{ color: pnlColor(t.pnl), fontWeight: 600 }}>${fmt(t.pnl)}</td>
                <td style={{ color: pnlColor(t.return_pct) }}>{fmtPct(t.return_pct)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {trades.length > 20 && (
        <button className="bt-show-all" onClick={() => setShowAll((v) => !v)}>
          {showAll ? 'Show Less' : `Show All ${trades.length} Trades`}
        </button>
      )}
    </>
  );
}

/* ─── Main Component ─── */
export default function BacktestPanel({ theme = 'dark' }) {
  const [symbols, setSymbols] = useState(['BTC/USDT']);
  const [timeframe, setTimeframe] = useState('5m');
  const [strategy, setStrategy] = useState('rl_agent');
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');
  const [initialCapital, setInitialCapital] = useState(100);
  const [maxLeverage, setMaxLeverage] = useState(10);
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [history, setHistory] = useState([]);

  // Load backtest history on mount
  useEffect(() => {
    (async () => {
      try {
        const data = await apiService.request('/api/backtest/run');
        setHistory(data.results || data.history || []);
      } catch {
        // Endpoint may not exist yet
      }
    })();
  }, []);

  const runBacktest = useCallback(async () => {
    setRunning(true);
    setError(null);
    setResult(null);

    try {
      const payload = {
        symbols: Array.isArray(symbols) ? symbols : [symbols],
        timeframe,
        strategy,
        start_date: startDate || undefined,
        end_date: endDate || undefined,
        initial_balance: Number(initialCapital),
        leverage: Number(maxLeverage),
      };

      const data = await apiService.request('/api/backtest/run', {
        method: 'POST',
        body: JSON.stringify(payload),
      });

      setResult(data);
      toast.success('Backtest completed!');
      setHistory((prev) => [data, ...prev].slice(0, 10));
    } catch (err) {
      setError(err.message);
      toast.error('Backtest failed: ' + err.message);
    } finally {
      setRunning(false);
    }
  }, [symbols, timeframe, strategy, startDate, endDate, initialCapital, maxLeverage]);

  const m = result?.metrics || result?.summary || {};

  return (
    <div className="bt-container" data-theme={theme}>
      {/* Header */}
      <div className="bt-header">
        <div>
          <h1 className="bt-title">🧪 Backtesting</h1>
          <p className="bt-subtitle">Run strategies against historical data</p>
        </div>
      </div>

      {/* Config Form */}
      <div className="bt-form">
        <div className="bt-form-grid">
          <label className="bt-field">
            <span>Symbol</span>
            <input
              type="text"
              value={symbols.join(', ')}
              onChange={(e) => setSymbols(e.target.value.split(',').map((s) => s.trim()))}
              placeholder="BTC/USDT, ETH/USDT"
            />
          </label>
          <label className="bt-field">
            <span>Timeframe</span>
            <select value={timeframe} onChange={(e) => setTimeframe(e.target.value)}>
              <option value="1m">1 Minute</option>
              <option value="5m">5 Minutes</option>
              <option value="15m">15 Minutes</option>
              <option value="1h">1 Hour</option>
              <option value="4h">4 Hours</option>
              <option value="1d">1 Day</option>
            </select>
          </label>
          <label className="bt-field">
            <span>Strategy</span>
            <select value={strategy} onChange={(e) => setStrategy(e.target.value)}>
              <option value="rl_agent">RL Agent (Trained Model)</option>
              <option value="buy_and_hold">Buy & Hold</option>
              <option value="moving_average">Moving Average Crossover</option>
              <option value="rsi_mean_reversion">RSI Mean Reversion</option>
            </select>
          </label>
          <label className="bt-field">
            <span>Start Date</span>
            <input type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} />
          </label>
          <label className="bt-field">
            <span>End Date</span>
            <input type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)} />
          </label>
          <label className="bt-field">
            <span>Initial Capital ($)</span>
            <input type="number" value={initialCapital} min={10} onChange={(e) => setInitialCapital(e.target.value)} />
          </label>
          <label className="bt-field">
            <span>Max Leverage</span>
            <input type="number" value={maxLeverage} min={1} max={125} onChange={(e) => setMaxLeverage(e.target.value)} />
          </label>
        </div>

        <button className="bt-run-btn" onClick={runBacktest} disabled={running}>
          {running ? '⏳ Running Backtest...' : '🚀 Run Backtest'}
        </button>
      </div>

      {/* Error */}
      {error && (
        <div className="bt-error">
          <span>⚠️</span>
          <p>{error}</p>
        </div>
      )}

      {/* Results */}
      {result && (
        <>
          {/* Key Metrics */}
          <div className="bt-metrics-grid">
            <div className="bt-metric">
              <span className="bt-metric-label">Total Return</span>
              <span className="bt-metric-value" style={{ color: pnlColor(m.total_return) }}>
                {fmtPct(m.total_return)}
              </span>
            </div>
            <div className="bt-metric">
              <span className="bt-metric-label">Sharpe Ratio</span>
              <span className="bt-metric-value">{fmt(m.sharpe_ratio)}</span>
            </div>
            <div className="bt-metric">
              <span className="bt-metric-label">Max Drawdown</span>
              <span className="bt-metric-value" style={{ color: '#ef4444' }}>
                {fmtPct(-(m.max_drawdown || 0))}
              </span>
            </div>
            <div className="bt-metric">
              <span className="bt-metric-label">Win Rate</span>
              <span className="bt-metric-value" style={{ color: (m.win_rate || 0) >= 50 ? '#10b981' : '#f59e0b' }}>
                {fmt(m.win_rate <= 1 ? m.win_rate * 100 : m.win_rate, 1)}%
              </span>
            </div>
            <div className="bt-metric">
              <span className="bt-metric-label">Total Trades</span>
              <span className="bt-metric-value">{m.total_trades ?? m.trades ?? '—'}</span>
            </div>
            <div className="bt-metric">
              <span className="bt-metric-label">Profit Factor</span>
              <span className="bt-metric-value">{fmt(m.profit_factor)}</span>
            </div>
            <div className="bt-metric">
              <span className="bt-metric-label">Final Equity</span>
              <span className="bt-metric-value">${fmt(m.final_equity ?? m.final_value)}</span>
            </div>
            <div className="bt-metric">
              <span className="bt-metric-label">Avg Trade</span>
              <span className="bt-metric-value" style={{ color: pnlColor(m.avg_trade_pnl) }}>
                ${fmt(m.avg_trade_pnl)}
              </span>
            </div>
          </div>

          {/* Equity Curve */}
          {result.equity_curve && result.equity_curve.length > 0 && (
            <div className="bt-section">
              <h3 className="bt-section-title">Equity Curve</h3>
              <EquityCurveChart points={result.equity_curve} />
            </div>
          )}

          {/* Trades */}
          {result.trades && result.trades.length > 0 && (
            <div className="bt-section">
              <h3 className="bt-section-title">
                Trade Log
                <span className="bt-count">{result.trades.length}</span>
              </h3>
              <TradeTable trades={result.trades} />
            </div>
          )}
        </>
      )}

      {/* History */}
      {history.length > 0 && (
        <div className="bt-section bt-history">
          <h3 className="bt-section-title">Recent Backtests</h3>
          <div className="bt-history-list">
            {history.slice(0, 5).map((h, i) => (
              <div key={i} className="bt-history-item" onClick={() => setResult(h)}>
                <div className="bt-history-info">
                  <strong>{h.strategy || strategy}</strong>
                  <span>{h.symbols?.join(', ') || '—'}</span>
                </div>
                <div className="bt-history-metrics">
                  <span style={{ color: pnlColor(h.metrics?.total_return || h.total_return) }}>
                    {fmtPct(h.metrics?.total_return || h.total_return)}
                  </span>
                  <span>Sharpe: {fmt(h.metrics?.sharpe_ratio || h.sharpe_ratio)}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Styles */}
      <style>{`
        .bt-container { padding: 24px; max-width: 1200px; margin: 0 auto; }
        .bt-container[data-theme="dark"] { color: #e2e8f0; }
        .bt-container[data-theme="light"] { color: #1e293b; }

        .bt-header { margin-bottom: 24px; }
        .bt-title { font-size: 1.75rem; font-weight: 700; margin: 0; }
        .bt-subtitle { font-size: 0.875rem; opacity: 0.6; margin: 4px 0 0; }

        .bt-form { background: rgba(128,128,128,0.06); border-radius: 12px; padding: 20px; margin-bottom: 24px; }
        .bt-form-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 16px; margin-bottom: 16px; }
        .bt-field { display: flex; flex-direction: column; gap: 4px; }
        .bt-field span { font-size: 0.8rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px; opacity: 0.7; }
        .bt-field input, .bt-field select {
          padding: 10px 12px; border-radius: 8px; border: 1px solid rgba(128,128,128,0.2);
          background: rgba(128,128,128,0.08); color: inherit; font-size: 0.9rem;
        }
        .bt-field input:focus, .bt-field select:focus { outline: none; border-color: #6366f1; }

        .bt-run-btn {
          width: 100%; padding: 14px; border-radius: 10px; border: none;
          background: linear-gradient(135deg, #6366f1, #8b5cf6); color: #fff;
          font-size: 1rem; font-weight: 600; cursor: pointer; transition: all 0.2s;
        }
        .bt-run-btn:hover:not(:disabled) { transform: translateY(-1px); box-shadow: 0 4px 15px rgba(99,102,241,0.3); }
        .bt-run-btn:disabled { opacity: 0.6; cursor: not-allowed; }

        .bt-error { text-align: center; padding: 24px; background: rgba(239,68,68,0.1); border-radius: 10px; margin-bottom: 24px; }
        .bt-error span { font-size: 1.5rem; display: block; margin-bottom: 8px; }

        .bt-metrics-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(140px, 1fr)); gap: 12px; margin-bottom: 24px; }
        .bt-metric {
          background: rgba(128,128,128,0.06); border-radius: 10px; padding: 14px; text-align: center;
        }
        .bt-metric-label { display: block; font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.5px; opacity: 0.6; margin-bottom: 6px; }
        .bt-metric-value { display: block; font-size: 1.3rem; font-weight: 700; }

        .bt-section { margin-bottom: 24px; }
        .bt-section-title { font-size: 1.1rem; font-weight: 600; margin-bottom: 12px; display: flex; align-items: center; gap: 8px; }
        .bt-count { background: rgba(99,102,241,0.2); color: #6366f1; padding: 2px 8px; border-radius: 12px; font-size: 0.75rem; }

        .bt-chart { position: relative; }
        .bt-chart-labels { display: flex; justify-content: space-between; font-size: 0.7rem; opacity: 0.5; margin-bottom: 4px; }
        .bt-chart-bars { display: flex; align-items: flex-end; gap: 1px; height: 120px; background: rgba(128,128,128,0.04); border-radius: 8px; padding: 4px; }
        .bt-bar-wrapper { flex: 1; height: 100%; display: flex; align-items: flex-end; }
        .bt-bar { width: 100%; border-radius: 2px 2px 0 0; min-height: 2px; transition: height 0.3s; }
        .bt-chart-x-label { text-align: center; font-size: 0.7rem; opacity: 0.4; margin-top: 4px; }

        .bt-table-wrap { overflow-x: auto; border-radius: 8px; border: 1px solid rgba(128,128,128,0.15); }
        .bt-table { width: 100%; border-collapse: collapse; font-size: 0.85rem; }
        .bt-table th { padding: 10px 12px; text-align: left; font-weight: 600; background: rgba(128,128,128,0.06); }
        .bt-table td { padding: 8px 12px; border-bottom: 1px solid rgba(128,128,128,0.08); }
        .bt-table tr:last-child td { border-bottom: none; }
        .bt-table tr:hover td { background: rgba(128,128,128,0.04); }
        .bt-time { font-size: 0.75rem; opacity: 0.7; }
        .bt-symbol { font-weight: 600; }
        .bt-badge { padding: 2px 6px; border-radius: 4px; font-size: 0.7rem; font-weight: 600; }
        .bt-long { background: rgba(16,185,129,0.15); color: #10b981; }
        .bt-short { background: rgba(239,68,68,0.15); color: #ef4444; }
        .bt-show-all { margin-top: 8px; padding: 8px 16px; border-radius: 8px; border: 1px solid rgba(128,128,128,0.2); background: transparent; color: #6366f1; cursor: pointer; }
        .bt-empty { text-align: center; padding: 24px; opacity: 0.5; }

        .bt-history-list { display: flex; flex-direction: column; gap: 8px; }
        .bt-history-item {
          display: flex; justify-content: space-between; align-items: center;
          padding: 12px 16px; border-radius: 8px; background: rgba(128,128,128,0.06);
          cursor: pointer; transition: background 0.2s;
        }
        .bt-history-item:hover { background: rgba(128,128,128,0.1); }
        .bt-history-info { display: flex; gap: 12px; align-items: center; }
        .bt-history-info span { opacity: 0.6; font-size: 0.85rem; }
        .bt-history-metrics { display: flex; gap: 16px; font-size: 0.85rem; }
      `}</style>
    </div>
  );
}