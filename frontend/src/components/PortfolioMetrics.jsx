/**
 * PortfolioMetrics.jsx – Live Portfolio Dashboard (Phase 6.4 / 8.1)
 *
 * Displays real-time portfolio metrics: Net Worth, Current Leverage,
 * Open Positions, Win Rate, Daily P&L, and Equity Curve.
 * Auto-refreshes every 3 seconds.
 */

import React, { useEffect, useState, useCallback } from 'react';
import toast from '../store/toastStore';
import apiService from '../utils/apiService';
import { CardSkeleton } from './LoadingSkeletons';

/* ─── helpers ─── */
const fmt = (n, dec = 2) => {
  if (n == null || isNaN(n)) return '—';
  return Number(n).toLocaleString('en-US', {
    minimumFractionDigits: dec,
    maximumFractionDigits: dec,
  });
};

const fmtPct = (n) => {
  if (n == null || isNaN(n)) return '—';
  return `${n >= 0 ? '+' : ''}${Number(n).toFixed(2)}%`;
};

const pnlColor = (v) => (v >= 0 ? 'var(--color-profit, #10b981)' : 'var(--color-loss, #ef4444)');

/* ─── Metric Card ─── */
function MetricCard({ label, value, sub, icon, accent }) {
  return (
    <div className="pm-card" style={{ borderTop: `3px solid ${accent || 'var(--color-primary, #6366f1)'}` }}>
      <div className="pm-card-header">
        <span className="pm-card-icon">{icon}</span>
        <span className="pm-card-label">{label}</span>
      </div>
      <div className="pm-card-value">{value}</div>
      {sub && <div className="pm-card-sub">{sub}</div>}
    </div>
  );
}

/* ─── Mini Equity Chart (CSS-only bar sparkline) ─── */
function EquitySparkline({ points = [] }) {
  if (points.length < 2) return null;
  const max = Math.max(...points);
  const min = Math.min(...points);
  const range = max - min || 1;
  const latest = points[points.length - 1];
  const first = points[0];
  const trendUp = latest >= first;

  return (
    <div className="pm-sparkline" title={`Equity: ${fmt(first)} → ${fmt(latest)}`}>
      {points.slice(-30).map((v, i) => {
        const h = Math.max(4, ((v - min) / range) * 48);
        return (
          <div
            key={i}
            className="pm-spark-bar"
            style={{
              height: `${h}px`,
              background: trendUp ? 'var(--color-profit, #10b981)' : 'var(--color-loss, #ef4444)',
              opacity: 0.4 + (i / 30) * 0.6,
            }}
          />
        );
      })}
    </div>
  );
}

/* ─── Open Positions Table ─── */
function PositionsTable({ positions = [] }) {
  if (!positions.length) {
    return <div className="pm-empty">No open positions</div>;
  }

  return (
    <div className="pm-table-wrap">
      <table className="pm-table">
        <thead>
          <tr>
            <th>Symbol</th>
            <th>Side</th>
            <th>Size</th>
            <th>Entry</th>
            <th>Current</th>
            <th>P&L</th>
            <th>Leverage</th>
          </tr>
        </thead>
        <tbody>
          {positions.map((p, i) => {
            const pnl = p.unrealized_pnl ?? p.pnl ?? 0;
            return (
              <tr key={i}>
                <td className="pm-symbol">{p.symbol || '—'}</td>
                <td>
                  <span className={`pm-badge ${p.side === 'long' ? 'pm-long' : 'pm-short'}`}>
                    {(p.side || 'hold').toUpperCase()}
                  </span>
                </td>
                <td>{fmt(p.size || p.quantity, 6)}</td>
                <td>${fmt(p.entry_price || p.avg_entry)}</td>
                <td>${fmt(p.current_price || p.mark_price)}</td>
                <td style={{ color: pnlColor(pnl), fontWeight: 600 }}>
                  ${fmt(pnl)} {p.pnl_pct != null && <small>({fmtPct(p.pnl_pct * 100)})</small>}
                </td>
                <td>{p.leverage ? `${p.leverage}×` : '1×'}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

/* ─── Main Component ─── */
export default function PortfolioMetrics({ theme = 'dark' }) {
  const [loading, setLoading] = useState(true);
  const [metrics, setMetrics] = useState(null);
  const [positions, setPositions] = useState([]);
  const [equityCurve, setEquityCurve] = useState([]);
  const [error, setError] = useState(null);
  const [autoRefresh, setAutoRefresh] = useState(true);

  const load = useCallback(async () => {
    try {
      // Try dedicated portfolio-metrics endpoint first, fallback to /portfolio
      let data;
      try {
        data = await apiService.request('/api/v1/portfolio/metrics');
      } catch {
        data = await apiService.getPortfolio();
      }

      const netWorth = data.net_worth ?? data.total_value ?? data.balance ?? 0;
      const dailyPnl = data.daily_pnl ?? data.pnl_today ?? 0;
      const dailyPnlPct = data.daily_pnl_pct ?? data.pnl_today_pct ?? 0;
      const winRate = data.win_rate ?? data.stats?.win_rate ?? 0;
      const leverage = data.current_leverage ?? data.max_leverage ?? 1;
      const openCount = data.open_positions_count ?? data.positions?.length ?? 0;
      const totalTrades = data.total_trades ?? data.stats?.total_trades ?? 0;

      setMetrics({
        netWorth,
        dailyPnl,
        dailyPnlPct,
        winRate: typeof winRate === 'number' && winRate <= 1 ? winRate * 100 : winRate,
        leverage,
        openCount,
        totalTrades,
        balance: data.balance ?? data.cash ?? netWorth,
        drawdown: data.max_drawdown ?? data.drawdown ?? 0,
      });

      setPositions(data.positions || data.open_positions || []);

      // Build equity curve from history or generate from net worth
      if (data.equity_curve && data.equity_curve.length > 0) {
        setEquityCurve(data.equity_curve);
      } else {
        setEquityCurve((prev) => {
          const next = [...prev, netWorth];
          return next.length > 60 ? next.slice(-60) : next;
        });
      }

      setError(null);
    } catch (err) {
      setError(err.message);
      // Don't spam toasts on auto-refresh
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
    if (!autoRefresh) return;
    const id = setInterval(load, 3000);
    return () => clearInterval(id);
  }, [load, autoRefresh]);

  if (loading) return <CardSkeleton />;

  if (error && !metrics) {
    return (
      <div className="pm-container" data-theme={theme}>
        <div className="pm-error">
          <span>⚠️</span>
          <p>Failed to load portfolio: {error}</p>
          <button onClick={load} className="pm-retry-btn">Retry</button>
        </div>
      </div>
    );
  }

  const m = metrics || {};

  return (
    <div className="pm-container" data-theme={theme}>
      {/* Header */}
      <div className="pm-header">
        <div>
          <h1 className="pm-title">📊 Portfolio Metrics</h1>
          <p className="pm-subtitle">Real-time portfolio monitoring</p>
        </div>
        <div className="pm-controls">
          <button
            className={`pm-toggle ${autoRefresh ? 'pm-active' : ''}`}
            onClick={() => setAutoRefresh((v) => !v)}
            title={autoRefresh ? 'Auto-refresh ON' : 'Auto-refresh OFF'}
          >
            {autoRefresh ? '🟢 Live' : '⏸️ Paused'}
          </button>
          <button className="pm-refresh-btn" onClick={() => { setLoading(true); load(); }}>
            🔄 Refresh
          </button>
        </div>
      </div>

      {/* Metric Cards Grid */}
      <div className="pm-grid">
        <MetricCard
          icon="💰"
          label="Net Worth"
          value={`$${fmt(m.netWorth)}`}
          sub={`Balance: $${fmt(m.balance)}`}
          accent="#6366f1"
        />
        <MetricCard
          icon="📈"
          label="Daily P&L"
          value={`$${fmt(m.dailyPnl)}`}
          sub={fmtPct(m.dailyPnlPct)}
          accent={pnlColor(m.dailyPnl)}
        />
        <MetricCard
          icon="🎯"
          label="Win Rate"
          value={`${fmt(m.winRate, 1)}%`}
          sub={`${m.totalTrades} total trades`}
          accent={m.winRate >= 60 ? '#10b981' : m.winRate >= 40 ? '#f59e0b' : '#ef4444'}
        />
        <MetricCard
          icon="⚡"
          label="Leverage"
          value={`${fmt(m.leverage, 1)}×`}
          sub={`${m.openCount} open positions`}
          accent="#8b5cf6"
        />
        <MetricCard
          icon="📉"
          label="Max Drawdown"
          value={fmtPct(-(m.drawdown || 0))}
          sub="Peak-to-trough"
          accent="#ef4444"
        />
        <MetricCard
          icon="💎"
          label="Cash Balance"
          value={`$${fmt(m.balance)}`}
          sub="Available margin"
          accent="#06b6d4"
        />
      </div>

      {/* Equity Curve Sparkline */}
      {equityCurve.length > 1 && (
        <div className="pm-section">
          <h3 className="pm-section-title">Equity Curve</h3>
          <EquitySparkline points={equityCurve} />
        </div>
      )}

      {/* Open Positions */}
      <div className="pm-section">
        <h3 className="pm-section-title">
          Open Positions
          <span className="pm-count">{positions.length}</span>
        </h3>
        <PositionsTable positions={positions}      />
      </div>

      {/* Inline styles (scoped) */}
      <style>{`
        .pm-container { padding: 24px; max-width: 1200px; margin: 0 auto; font-family: inherit; }
        .pm-container[data-theme="dark"] { color: #e2e8f0; }
        .pm-container[data-theme="light"] { color: #1e293b; }

        .pm-header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 24px; flex-wrap: wrap; gap: 12px; }
        .pm-title { font-size: 1.75rem; font-weight: 700; margin: 0; }
        .pm-subtitle { font-size: 0.875rem; opacity: 0.6; margin: 4px 0 0; }
        .pm-controls { display: flex; gap: 8px; align-items: center; }
        .pm-toggle, .pm-refresh-btn, .pm-retry-btn {
          padding: 8px 16px; border-radius: 8px; border: 1px solid rgba(128,128,128,0.2);
          background: rgba(128,128,128,0.08); cursor: pointer; font-size: 0.85rem; transition: all 0.2s;
        }
        .pm-toggle:hover, .pm-refresh-btn:hover { background: rgba(128,128,128,0.15); }
        .pm-toggle.pm-active { border-color: #10b981; color: #10b981; }

        .pm-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 16px; margin-bottom: 24px; }
        .pm-card {
          background: rgba(128,128,128,0.06); border-radius: 12px; padding: 16px;
          transition: transform 0.2s, box-shadow 0.2s;
        }
        .pm-card:hover { transform: translateY(-2px); box-shadow: 0 4px 12px rgba(0,0,0,0.1); }
        .pm-card-header { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
        .pm-card-icon { font-size: 1.2rem; }
        .pm-card-label { font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.5px; opacity: 0.7; }
        .pm-card-value { font-size: 1.5rem; font-weight: 700; margin-bottom: 4px; }
        .pm-card-sub { font-size: 0.75rem; opacity: 0.5; }

        .pm-section { margin-bottom: 24px; }
        .pm-section-title { font-size: 1.1rem; font-weight: 600; margin-bottom: 12px; display: flex; align-items: center; gap: 8px; }
        .pm-count { background: rgba(99,102,241,0.2); color: #6366f1; padding: 2px 8px; border-radius: 12px; font-size: 0.75rem; }

        .pm-sparkline { display: flex; align-items: flex-end; gap: 2px; height: 56px; padding: 4px 0; }
        .pm-spark-bar { flex: 1; min-width: 4px; border-radius: 2px 2px 0 0; transition: height 0.3s; }

        .pm-table-wrap { overflow-x: auto; border-radius: 8px; border: 1px solid rgba(128,128,128,0.15); }
        .pm-table { width: 100%; border-collapse: collapse; font-size: 0.85rem; }
        .pm-table th { padding: 10px 12px; text-align: left; font-weight: 600; background: rgba(128,128,128,0.06); border-bottom: 1px solid rgba(128,128,128,0.15); }
        .pm-table td { padding: 10px 12px; border-bottom: 1px solid rgba(128,128,128,0.08); }
        .pm-table tr:last-child td { border-bottom: none; }
        .pm-table tr:hover td { background: rgba(128,128,128,0.04); }
        .pm-symbol { font-weight: 600; }
        .pm-badge { padding: 2px 8px; border-radius: 4px; font-size: 0.75rem; font-weight: 600; }
        .pm-long { background: rgba(16,185,129,0.15); color: #10b981; }
        .pm-short { background: rgba(239,68,68,0.15); color: #ef4444; }

        .pm-empty { text-align: center; padding: 32px; opacity: 0.5; font-style: italic; }
        .pm-error { text-align: center; padding: 48px; }
        .pm-error span { font-size: 2rem; display: block; margin-bottom: 12px; }
      `}</style>
    </div>
  );
}