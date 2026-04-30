/**
 * XAI Explainability Panel
 * 
 * Displays SHAP-like feature importance breakdown and narrative explanation
 * for RL agent trading decisions. Integrates with /api/xai/* endpoints.
 * 
 * Features:
 * - Horizontal bar chart of feature importance with direction indicators
 * - Narrative explanation (MiMo-style reasoning)
 * - Risk assessment badge
 * - Auto-refresh polling
 */
import React, { useState, useEffect, useCallback } from 'react';
import { getXaiFeatureImportance, getXaiHistory } from '../services/api.js';

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
  color: '#00d4ff',
  margin: 0,
};

const badgeStyle = (level) => ({
  display: 'inline-block',
  padding: '4px 12px',
  borderRadius: 20,
  fontSize: 12,
  fontWeight: 600,
  textTransform: 'uppercase',
  background:
    level === 'extreme' ? '#ff4444' :
    level === 'situasi' ? '#ffaa00' : '#44cc44',
  color: '#fff',
});

const barContainerStyle = {
  display: 'flex',
  flexDirection: 'column',
  gap: 8,
  marginBottom: 16,
};

const barRowStyle = {
  display: 'flex',
  alignItems: 'center',
  gap: 8,
};

const barLabelStyle = {
  width: 160,
  fontSize: 13,
  fontWeight: 500,
  textAlign: 'right',
  flexShrink: 0,
  overflow: 'hidden',
  textOverflow: 'ellipsis',
  whiteSpace: 'nowrap',
};

const barTrackStyle = {
  flex: 1,
  height: 22,
  background: '#1e1e3a',
  borderRadius: 4,
  overflow: 'hidden',
  position: 'relative',
};

const barFillStyle = (pct, direction) => ({
  height: '100%',
  width: `${Math.min(Math.abs(pct), 100)}%`,
  background: direction === '+' ? 'linear-gradient(90deg, #00b894, #00d4ff)' : 'linear-gradient(90deg, #ff6b6b, #ee5a24)',
  borderRadius: 4,
  transition: 'width 0.6s ease',
  display: 'flex',
  alignItems: 'center',
  paddingLeft: 6,
});

const barValueStyle = {
  fontSize: 11,
  fontWeight: 700,
  color: '#fff',
  whiteSpace: 'nowrap',
};

const narrativeStyle = {
  background: '#0d1b2a',
  borderRadius: 8,
  padding: 14,
  fontSize: 14,
  lineHeight: 1.6,
  color: '#b8c6db',
  borderLeft: '3px solid #00d4ff',
  marginBottom: 12,
};

const statsRowStyle = {
  display: 'flex',
  gap: 16,
  fontSize: 12,
  color: '#8899aa',
};

const statItemStyle = {
  display: 'flex',
  flexDirection: 'column',
  alignItems: 'center',
};

const statValueStyle = {
  fontSize: 16,
  fontWeight: 700,
  color: '#00d4ff',
};

const emptyStyle = {
  textAlign: 'center',
  padding: 30,
  color: '#667788',
  fontSize: 14,
};

const refreshBtnStyle = {
  background: 'transparent',
  border: '1px solid #2a2a4a',
  color: '#8899aa',
  padding: '4px 12px',
  borderRadius: 6,
  cursor: 'pointer',
  fontSize: 12,
};

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------
export default function XaiPanel({ autoRefreshMs = 30000 }) {
  const [data, setData] = useState(null);
  const [history, setHistory] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [importance, hist] = await Promise.all([
        getXaiFeatureImportance(),
        getXaiHistory(),
      ]);
      setData(importance);
      setHistory(hist.history || []);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
    if (autoRefreshMs > 0) {
      const timer = setInterval(fetchData, autoRefreshMs);
      return () => clearInterval(timer);
    }
  }, [fetchData, autoRefreshMs]);

  // Sort features by importance
  const features = (data?.feature_importance || [])
    .slice()
    .sort((a, b) => (b.importance_pct || 0) - (a.importance_pct || 0))
    .slice(0, 10); // top 10

  return (
    <div style={panelStyle}>
      <div style={headerStyle}>
        <h3 style={titleStyle}>🧠 XAI — Explainable AI</h3>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          {data?.risk_assessment && (
            <span style={badgeStyle(data.risk_assessment)}>
              Risk: {data.risk_assessment}
            </span>
          )}
          <button style={refreshBtnStyle} onClick={fetchData} disabled={loading}>
            {loading ? '⟳' : '↻'} Refresh
          </button>
        </div>
      </div>

      {error && (
        <div style={{ ...emptyStyle, color: '#ff6b6b' }}>⚠ Error: {error}</div>
      )}

      {!error && loading && !data && (
        <div style={emptyStyle}>Loading XAI data...</div>
      )}

      {!error && data && features.length === 0 && (
        <div style={emptyStyle}>
          No feature importance data available yet. The XAI service will populate
          this panel once the RL agent generates predictions.
        </div>
      )}

      {/* Feature Importance Bar Chart */}
      {features.length > 0 && (
        <div style={barContainerStyle}>
          {features.map((feat, idx) => (
            <div key={idx} style={barRowStyle}>
              <span style={barLabelStyle} title={feat.feature || feat.feature_name}>
                {feat.feature || feat.feature_name || `Feature ${idx}`}
              </span>
              <div style={barTrackStyle}>
                <div style={barFillStyle(feat.importance_pct, feat.direction)}>
                  <span style={barValueStyle}>
                    {feat.direction === '+' ? '+' : '-'}{(feat.importance_pct || 0).toFixed(1)}%
                  </span>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Narrative */}
      {data?.narrative && (
        <div style={narrativeStyle}>
          <strong style={{ color: '#00d4ff' }}>💡 AI Reasoning:</strong><br />
          {data.narrative}
        </div>
      )}

      {/* Stats */}
      {data?.stats && (
        <div style={statsRowStyle}>
          <div style={statItemStyle}>
            <span style={statValueStyle}>{data.stats.explanation_count || 0}</span>
            <span>Explanations</span>
          </div>
          <div style={statItemStyle}>
            <span style={statValueStyle}>{history.length}</span>
            <span>History</span>
          </div>
        </div>
      )}
    </div>
  );
}