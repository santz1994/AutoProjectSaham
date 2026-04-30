/**
 * API Service - XAI & Autonomy Endpoints
 *
 * Centralised helper functions consumed by XaiPanel.jsx and AutonomyControl.jsx.
 * Delegates to the global ApiService (../utils/apiService.js) for consistent
 * auth / CSRF / error handling.
 */

import apiService from '../utils/apiService';

// ---------------------------------------------------------------------------
// XAI Explainability
// ---------------------------------------------------------------------------

/**
 * Get XAI explanation for a symbol's latest RL decision.
 * @param {string} symbol  – e.g. "BTC/USDT"
 * @returns {Promise<{feature_contributions: Array, narrative: string, action: string, risk_assessment: string, timestamp: string}>}
 */
export async function getXaiExplanation(symbol) {
  const safe = encodeURIComponent(String(symbol || '').trim());
  if (!safe) throw new Error('symbol is required');
  return apiService.request(`/api/xai/explain/${safe}`);
}

/**
 * Get XAI feature importance for the XaiPanel.
 * Calls POST /api/xai/explain with default values to get the latest explanation.
 * @returns {Promise<{feature_importance: Array, narrative: string, risk_assessment: string, stats: object}>}
 */
export async function getXaiFeatureImportance() {
  try {
    const result = await apiService.request('/api/xai/explain', {
      method: 'POST',
      body: JSON.stringify({
        symbol: 'BTC/USDT',
        action: 'BUY',
      }),
    });
    // Normalize backend field names to what XaiPanel expects
    return {
      feature_importance: result.feature_contributions || [],
      narrative: result.narrative || '',
      risk_assessment: result.risk_assessment || 'unknown',
      stats: result.stats || {},
      confidence_score: result.confidence_score || 0,
    };
  } catch (err) {
    // If service unavailable, return empty state
    console.warn('XAI feature importance unavailable:', err.message);
    return {
      feature_importance: [],
      narrative: '',
      risk_assessment: 'unavailable',
      stats: {},
      confidence_score: 0,
    };
  }
}

/**
 * Get recent XAI explanation history.
 * @param {number} limit
 * @returns {Promise<{explanations: Array, total: number}>}
 */
export async function getXaiHistory(limit = 20) {
  const safeLimit = Math.max(1, Math.min(100, Number(limit) || 20));
  return apiService.request(`/api/xai/history?limit=${safeLimit}`);
}

/**
 * Get XAI service stats.
 * @returns {Promise<{total_explanations: number, avg_features: number}>}
 */
export async function getXaiStats() {
  return apiService.request('/api/xai/stats');
}

// ---------------------------------------------------------------------------
// Autonomy Control
// ---------------------------------------------------------------------------

/**
 * Get current autonomy status (level, kill-switch state, stats).
 * @returns {Promise<{level: number, level_name: string, kill_switch_active: boolean, stats: object}>}
 */
export async function getAutonomyStatus() {
  return apiService.request('/api/autonomy/status');
}

/**
 * Set the autonomy level (1=signal_only, 2=human_confirm, 3=full_auto).
 * @param {number} level
 */
export async function setAutonomyLevel(level) {
  const safeLevel = Math.max(1, Math.min(3, Number(level) || 1));
  return apiService.request('/api/autonomy/level', {
    method: 'POST',
    body: JSON.stringify({ level: safeLevel }),
  });
}

/**
 * Toggle kill-switch on/off.
 * @param {boolean} active – true to activate, false to deactivate
 */
export async function toggleKillSwitch(active) {
  return apiService.request('/api/autonomy/kill-switch', {
    method: 'POST',
    body: JSON.stringify({ active: !!active }),
  });
}

/**
 * Get list of pending orders (autonomy level 2).
 * @returns {Promise<{pending_orders: Array, total: number}>}
 */
export async function getAutonomyPendingOrders() {
  return apiService.request('/api/autonomy/pending-orders');
}

/**
 * Approve a pending order by ID.
 * @param {string} orderId
 */
export async function approveOrder(orderId) {
  const safe = encodeURIComponent(String(orderId || '').trim());
  if (!safe) throw new Error('orderId is required');
  return apiService.request(`/api/autonomy/approve/${safe}`, { method: 'POST' });
}

/**
 * Reject a pending order by ID.
 * @param {string} orderId
 */
export async function rejectOrder(orderId) {
  const safe = encodeURIComponent(String(orderId || '').trim());
  if (!safe) throw new Error('orderId is required');
  return apiService.request(`/api/autonomy/reject/${safe}`, { method: 'POST' });
}