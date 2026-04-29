/**
 * Autonomy Control Panel
 * 
 * Provides UI for:
 * - 3-level autonomy slider (SIGNAL_ONLY / HUMAN_CONFIRM / FULL_AUTO)
 * - Kill switch toggle
 * - Pending orders queue with approve/reject
 * - Live stats display
 * 
 * Integrates with /api/autonomy/* endpoints.
 */
import React, { useState, useEffect, useCallback } from 'react';
import {
  getAutonomyStatus,
  setAutonomyLevel,
  toggleKillSwitch,
  getAutonomyPendingOrders,
  approveOrder,
  rejectOrder,
} from '../services/api.js';

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------
const LEVELS = [
  { value: 1, name: 'SIGNAL_ONLY', label: 'Signal Only', icon: '📡', desc: 'AI generates signals only — no orders executed' },
  { value: 2, name: 'HUMAN_CONFIRM', label: 'Human Confirm', icon: '🤝', desc: 'AI drafts orders — requires your approval' },
  { value: 3, name: 'FULL_AUTO', label: 'Full Auto', icon: '🤖', desc: 'AI executes orders autonomously' },
];

// ---------------------------------------------------------------------------
// Styles
// ---------------------------------------------------------------------------
const panelStyle = {
  background: 'linear-gradient(135deg, #1a1a2e 0%, #16213e 100%)',
  borderRadius: 12,
  padding: 20,
  color: '#e0e0e0',
  fontFamily: "'Inter', 'Segoe UI', sans-serif",
  border: '1px solid #2a2a4a',
  boxShadow: '0 4px 24px rgba(0,0,0,0.3)',
};

const headerStyle = {
  display: 'flex',
  justifyContent: 'space-between',
  alignItems: 'center',
  marginBottom: 16,
};

const titleStyle = {
  fontSize: 18,
  fontWeight: 700,
  color: '#ff9f43',
  margin: 0,
};

const sliderContainerStyle = {
  display: 'flex',
  gap: 8,
  marginBottom: 16,
};

const levelBtnStyle = (active, disabled) => ({
  flex: 1,
  padding: '12px 8px',
  borderRadius: 8,
  border: active ? '2px solid #00d4ff' : '2px solid #2a2a4a',
  background: active ? 'rgba(0,212,255,0.15)' : '#0d1b2a',
  color: active ? '#00d4ff' : '#667788',
  cursor: disabled ? 'not-allowed' : 'pointer',
  textAlign: 'center',
  transition: 'all 0.3s ease',
  opacity: disabled ? 0.5 : 1,
});

const levelIconStyle = {
  fontSize: 24,
  display: 'block',
  marginBottom: 4,
};

const levelLabelStyle = {
  fontSize: 12,
  fontWeight: 600,
};

const killSwitchContainerStyle = {
  display: 'flex',
  justifyContent: 'space-between',
  alignItems: 'center',
  padding: '12px 16px',
  background: '#0d1b2a',
  borderRadius: 8,
  marginBottom: 16,
  border: '1px solid #2a2a4a',
};

const killSwitchBtnStyle = (active) => ({
  padding: '8px 24px',
  borderRadius: 6,
  border: 'none',
  background: active ? '#ff4444' : '#44cc44',
  color: '#fff',
  fontWeight: 700,
  fontSize: 13,
  cursor: 'pointer',
  transition: 'all 0.3s ease',
});

const orderCardStyle = {
  background: '#0d1b2a',
  borderRadius: 8,
  padding: 12,
  marginBottom: 8,
  border: '1px solid #2a2a4a',
  display: 'flex',
  justifyContent: 'space-between',
  alignItems: 'center',
};

const orderBtnStyle = (type) => ({
  padding: '6px 16px',
  borderRadius: 4,
  border: 'none',
  background: type === 'approve' ? '#44cc44' : '#ff4444',
  color: '#fff',
  fontWeight: 600,
  fontSize: 12,
  cursor: 'pointer',
  marginLeft: 8,
});

const statsRowStyle = {
  display: 'flex',
  gap: 16,
  fontSize: 12,
  color: '#8899aa',
  marginTop: 12,
};

const statItemStyle = {
  display: 'flex',
  flexDirection: 'column',
  alignItems: 'center',
};

const statValueStyle = {
  fontSize: 16,
  fontWeight: 700,
  color: '#ff9f43',
};

const emptyStyle = {
  textAlign: 'center',
  padding: 20,
  color: '#667788',
  fontSize: 13,
};

const descStyle = {
  fontSize: 12,
  color: '#8899aa',
  textAlign: 'center',
  marginBottom: 16,
  fontStyle: 'italic',
};

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------
export default function AutonomyControl({ autoRefreshMs = 15000 }) {
  const [status, setStatus] = useState(null);
  const [pendingOrders, setPendingOrders] = useState([]);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState(false);
  const [error, setError] = useState(null);

  const fetchStatus = useCallback(async () => {
    try {
      const [st, orders] = await Promise.all([
        getAutonomyStatus(),
        getAutonomyPendingOrders(),
      ]);
      setStatus(st);
      setPendingOrders(orders.pending_orders || []);
      setError(null);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchStatus();
    if (autoRefreshMs > 0) {
      const timer = setInterval(fetchStatus, autoRefreshMs);
      return () => clearInterval(timer);
    }
  }, [fetchStatus, autoRefreshMs]);

  const handleLevelChange = async (level) => {
    if (actionLoading) return;
    setActionLoading(true);
    try {
      await setAutonomyLevel(level);
      await fetchStatus();
    } catch (err) {
      setError(err.message);
    } finally {
      setActionLoading(false);
    }
  };

  const handleKillSwitch = async () => {
    if (actionLoading) return;
    setActionLoading(true);
    try {
      const currentlyActive = status?.kill_switch_active;
      await toggleKillSwitch(!currentlyActive);
      await fetchStatus();
    } catch (err) {
      setError(err.message);
    } finally {
      setActionLoading(false);
    }
  };

  const handleApprove = async (orderId) => {
    setActionLoading(true);
    try {
      await approveOrder(orderId);
      await fetchStatus();
    } catch (err) {
      setError(err.message);
    } finally {
      setActionLoading(false);
    }
  };

  const handleReject = async (orderId) => {
    setActionLoading(true);
    try {
      await rejectOrder(orderId);
      await fetchStatus();
    } catch (err) {
      setError(err.message);
    } finally {
      setActionLoading(false);
    }
  };

  const currentLevel = status?.level || 1;
  const killActive = status?.kill_switch_active || false;
  const currentLevelInfo = LEVELS.find(l => l.value === currentLevel) || LEVELS[0];

  return (
    <div style={panelStyle}>
      <div style={headerStyle}>
        <h3 style={titleStyle}>🎛️ Autonomy Control</h3>
        {killActive && (
          <span style={{
            display: 'inline-block',
            padding: '4px 12px',
            borderRadius: 20,
            fontSize: 12,
            fontWeight: 700,
            background: '#ff4444',
            color: '#fff',
            animation: 'pulse 1.5s infinite',
          }}>
            🚨 KILL SWITCH ACTIVE
          </span>
        )}
      </div>

      {error && (
        <div style={{ ...emptyStyle, color: '#ff6b6b' }}>⚠ {error}</div>
      )}

      {/* Autonomy Level Slider */}
      <div style={sliderContainerStyle}>
        {LEVELS.map(level => (
          <button
            key={level.value}
            style={levelBtnStyle(currentLevel === level.value, actionLoading || killActive)}
            onClick={() => handleLevelChange(level.value)}
            disabled={actionLoading || killActive}
          >
            <span style={levelIconStyle}>{level.icon}</span>
            <span style={levelLabelStyle}>{level.label}</span>
          </button>
        ))}
      </div>
      <div style={descStyle}>{currentLevelInfo.desc}</div>

      {/* Kill Switch */}
      <div style={killSwitchContainerStyle}>
        <div>
          <div style={{ fontWeight: 600, fontSize: 14 }}>
            {killActive ? '🔴 Kill Switch is ACTIVE' : '🟢 Kill Switch is OFF'}
          </div>
          <div style={{ fontSize: 12, color: '#8899aa', marginTop: 2 }}>
            {killActive ? 'All trades are blocked. Deactivate to resume.' : 'Emergency stop: blocks all trading instantly.'}
          </div>
        </div>
        <button
          style={killSwitchBtnStyle(!killActive)}
          onClick={handleKillSwitch}
          disabled={actionLoading}
        >
          {killActive ? 'Deactivate' : '🚨 ACTIVATE'}
        </button>
      </div>

      {/* Pending Orders (Level 2) */}
      {currentLevel === 2 && (
        <div>
          <h4 style={{ fontSize: 14, fontWeight: 600, color: '#ff9f43', marginBottom: 8 }}>
            📋 Pending Orders ({pendingOrders.length})
          </h4>
          {pendingOrders.length === 0 && (
            <div style={emptyStyle}>No pending orders awaiting approval.</div>
          )}
          {pendingOrders.map((order, idx) => (
            <div key={order.order_id || idx} style={orderCardStyle}>
              <div>
                <div style={{ fontWeight: 600, fontSize: 14 }}>
                  {order.symbol || 'N/A'} — {order.action || 'N/A'}
                </div>
                <div style={{ fontSize: 12, color: '#8899aa' }}>
                  Size: {order.size || '—'} | ID: {(order.order_id || '').slice(0, 8)}...
                </div>
              </div>
              <div>
                <button
                  style={orderBtnStyle('approve')}
                  onClick={() => handleApprove(order.order_id)}
                  disabled={actionLoading}
                >
                  ✓ Approve
                </button>
                <button
                  style={orderBtnStyle('reject')}
                  onClick={() => handleReject(order.order_id)}
                  disabled={actionLoading}
                >
                  ✗ Reject
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Stats */}
      {status?.stats && (
        <div style={statsRowStyle}>
          <div style={statItemStyle}>
            <span style={statValueStyle}>{status.stats.orders_submitted || 0}</span>
            <span>Submitted</span>
          </div>
          <div style={statItemStyle}>
            <span style={statValueStyle}>{status.stats.orders_approved || 0}</span>
            <span>Approved</span>
          </div>
          <div style={statItemStyle}>
            <span style={statValueStyle}>{status.stats.orders_rejected || 0}</span>
            <span>Rejected</span>
          </div>
          <div style={statItemStyle}>
            <span style={statValueStyle}>{status.stats.orders_executed || 0}</span>
            <span>Executed</span>
          </div>
        </div>
      )}
    </div>
  );
}