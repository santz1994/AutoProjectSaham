/**
 * API Service - Real Backend Integration
 * Replaces all mock data with actual API calls
 */

import { getAPIBase } from './authService';

function readCookieValue(name) {
  if (typeof document === 'undefined') {
    return '';
  }

  const encodedName = encodeURIComponent(String(name || '').trim());
  if (!encodedName) {
    return '';
  }

  const chunks = String(document.cookie || '').split(';');
  for (const rawChunk of chunks) {
    const chunk = rawChunk.trim();
    if (!chunk) {
      continue;
    }
    if (!chunk.startsWith(`${encodedName}=`)) {
      continue;
    }

    const value = chunk.slice(encodedName.length + 1);
    try {
      return decodeURIComponent(value);
    } catch {
      return value;
    }
  }

  return '';
}

function isMutatingMethod(method) {
  const normalized = String(method || 'GET').trim().toUpperCase();
  return normalized === 'POST' || normalized === 'PUT' || normalized === 'PATCH' || normalized === 'DELETE';
}

class ApiService {
  constructor() {
    this.baseURL = getAPIBase();
  }

  // Helper method for API calls with error handling
  async request(endpoint, options = {}) {
    const url = `${this.baseURL}${endpoint}`;
    const method = String(options.method || 'GET').trim().toUpperCase();
    const csrfToken = isMutatingMethod(method) ? readCookieValue('csrf_token') : '';

    const defaultOptions = {
      credentials: 'include', // Include cookies for auth
      headers: {
        'Content-Type': 'application/json',
        ...(csrfToken ? { 'X-CSRF-Token': csrfToken } : {}),
        ...options.headers,
      },
    };

    try {
      const response = await fetch(url, { ...defaultOptions, ...options });
      
      if (!response.ok) {
        const error = await response.json().catch(() => ({ detail: response.statusText }));
        throw new Error(error.detail || `HTTP ${response.status}`);
      }

      // Handle empty responses
      const text = await response.text();
      return text ? JSON.parse(text) : null;
    } catch (error) {
      console.error(`API Error [${endpoint}]:`, error);
      throw error;
    }
  }

  isNotFoundError(error) {
    const message = String(error?.message || '');
    return message.includes('404') || message.includes('Not Found');
  }

  // ============ Portfolio API ============
  async getPortfolio() {
    return this.request('/api/portfolio');
  }

  async refreshPortfolio() {
    return this.request('/api/portfolio/refresh', { method: 'POST' });
  }

  // ============ Bot Status API ============
  async getBotStatus() {
    return this.request('/api/bot/status');
  }

  async startBot() {
    return this.request('/api/bot/start', { method: 'POST' });
  }

  async stopBot() {
    return this.request('/api/bot/stop', { method: 'POST' });
  }

  async pauseBot() {
    return this.request('/api/bot/pause', { method: 'POST' });
  }

  async getKillSwitchState() {
    return this.request('/api/system/kill-switch');
  }

  async activateKillSwitch(reason = 'Emergency stop from UI', actor = 'ui-navbar', options = {}) {
    const challengeCode = String(options?.challengeCode || '').trim();
    return this.request('/api/system/kill-switch/activate', {
      method: 'POST',
      body: JSON.stringify({
        reason,
        actor,
        ...(challengeCode ? { challengeCode } : {}),
      }),
    });
  }

  async deactivateKillSwitch(reason = 'Manual resume from UI', actor = 'ui-navbar', options = {}) {
    const challengeCode = String(options?.challengeCode || '').trim();
    return this.request('/api/system/kill-switch/deactivate', {
      method: 'POST',
      body: JSON.stringify({
        reason,
        actor,
        ...(challengeCode ? { challengeCode } : {}),
      }),
    });
  }

  async getExecutionPendingOrders(limit = 200) {
    const safeLimit = Math.max(1, Math.min(1000, Number(limit) || 200));
    return this.request(`/api/system/execution/pending-orders?limit=${safeLimit}`);
  }

  // ============ Signals API ============
  async getTopSignals(limit = 10) {
    return this.request(`/api/signals?limit=${limit}`);
  }

  async getSignalById(id) {
    return this.request(`/api/signals/${id}`);
  }

  // ============ Market Data API ============
  async getMarketSentiment() {
    return this.request('/api/market/sentiment');
  }

  async getSectorHeatmap() {
    return this.request('/api/market/sectors');
  }

  async getTopMovers() {
    return this.request('/api/market/movers');
  }

  async getMarketUniverse(limit = 80, market = 'stocks') {
    const safeLimit = Math.max(10, Math.min(500, Number(limit) || 80));
    const safeMarket = encodeURIComponent(String(market || 'stocks').trim().toLowerCase());
    return this.request(`/api/market/universe?limit=${safeLimit}&market=${safeMarket}`);
  }

  async getMarketNews(limit = 10) {
    return this.request(`/api/market/news?limit=${limit}`);
  }

  // ============ Charts API ============
  async getChartData(symbol, timeframe = '1d', limit = 100) {
    return this.request(`/api/charts/candles/${symbol}?timeframe=${timeframe}&limit=${limit}`);
  }

  async getChartMetadata(symbol) {
    return this.request(`/api/charts/metadata/${symbol}`);
  }

  async getTradingStatus() {
    return this.request('/api/charts/trading-status');
  }

  async getAIProjection(symbol, timeframe = '1d', horizon = 16, market = 'stocks') {
    const safeSymbol = encodeURIComponent(symbol);
    const safeTimeframe = encodeURIComponent(timeframe);
    const safeHorizon = Number.isFinite(Number(horizon)) ? Number(horizon) : 16;
    const safeMarket = encodeURIComponent(String(market || 'stocks').trim().toLowerCase());
    return this.request(
      `/api/ai/projection/${safeSymbol}?timeframe=${safeTimeframe}&horizon=${safeHorizon}&market=${safeMarket}`
    );
  }

  // ============ Strategies API ============
  async getStrategies() {
    return this.request('/api/strategies');
  }

  async getStrategyById(id) {
    return this.request(`/api/strategies/${id}`);
  }

  async deployStrategy(strategyId) {
    return this.request(`/api/strategies/${strategyId}/deploy`, { method: 'POST' });
  }

  async backtestStrategy(strategyId, params = {}) {
    return this.request(`/api/strategies/${strategyId}/backtest`, {
      method: 'POST',
      body: JSON.stringify(params),
    });
  }

  // ============ Trade Logs API ============
  async getTradeLogs(params = {}) {
    const queryString = new URLSearchParams(params).toString();
    return this.request(`/api/trades${queryString ? '?' + queryString : ''}`);
  }

  async getTradeById(id) {
    return this.request(`/api/trades/${id}`);
  }

  async exportTrades(format = 'csv') {
    return this.request(`/api/trades/export?format=${format}`);
  }

  // ============ Portfolio Health API ============
  async getPortfolioHealth() {
    return this.request('/api/portfolio/health');
  }

  // ============ Recent Activity API ============
  async getRecentActivity(limit = 10) {
    return this.request(`/api/activity?limit=${limit}`);
  }

  // ============ Notifications API ============
  async getNotifications(userId, limit = 30, offset = 0) {
    const safeUser = encodeURIComponent(String(userId || '').trim());
    if (!safeUser) {
      throw new Error('userId is required for notification history');
    }
    const safeLimit = Math.max(1, Math.min(200, Number(limit) || 30));
    const safeOffset = Math.max(0, Number(offset) || 0);
    return this.request(`/api/notifications/history/${safeUser}?limit=${safeLimit}&offset=${safeOffset}`);
  }

  async getUnreadNotificationsCount(userId) {
    const safeUser = encodeURIComponent(String(userId || '').trim());
    if (!safeUser) {
      throw new Error('userId is required for unread notification count');
    }
    return this.request(`/api/notifications/unread/${safeUser}`);
  }

  async markNotificationRead(id, userId) {
    const safeId = encodeURIComponent(String(id || '').trim());
    if (!safeId) {
      throw new Error('notification id is required');
    }

    const safeUser = encodeURIComponent(String(userId || '').trim());
    const query = safeUser ? `?user_id=${safeUser}` : '';
    return this.request(`/api/notifications/mark-read/${safeId}${query}`, { method: 'POST' });
  }

  async markAllNotificationsRead(userId) {
    const history = await this.getNotifications(userId, 100, 0);
    const notifications = Array.isArray(history?.notifications) ? history.notifications : [];
    const unread = notifications.filter((item) => !item.read);

    await Promise.all(unread.map((item) => this.markNotificationRead(item.id, userId)));
    return { success: true, count: unread.length };
  }

  // ============ User Settings API ============
  async getUserSettings() {
    return this.request('/api/user/settings');
  }

  async updateUserSettings(settings) {
    return this.request('/api/user/settings', {
      method: 'PUT',
      body: JSON.stringify(settings),
    });
  }

  async getTwoFactorStatus() {
    return this.request('/auth/2fa/status');
  }

  async beginTwoFactorEnrollment() {
    return this.request('/auth/2fa/enroll', {
      method: 'POST',
    });
  }

  async verifyTwoFactorEnrollment(code) {
    return this.request('/auth/2fa/verify', {
      method: 'POST',
      body: JSON.stringify({ code: String(code || '').trim() }),
    });
  }

  async disableTwoFactor(code) {
    return this.request('/auth/2fa/disable', {
      method: 'POST',
      body: JSON.stringify({ code: String(code || '').trim() }),
    });
  }

  // ============ Broker Connection API ============
  async getAvailableBrokers() {
    return this.request('/api/brokers/available');
  }

  async getBrokerConnection() {
    return this.request('/api/broker/connection');
  }

  async connectBroker(payload) {
    return this.request('/api/broker/connect', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  }

  async disconnectBroker() {
    return this.request('/api/broker/disconnect', {
      method: 'POST',
    });
  }

  async getBrokerFeatureFlags() {
    return this.request('/api/brokers/feature-flags');
  }

  async updateBrokerFeatureFlag(providerId, payload) {
    return this.request(`/api/brokers/feature-flags/${providerId}`, {
      method: 'PUT',
      body: JSON.stringify(payload),
    });
  }

  // ============ AI Monitor API ============
  async getAIOverview() {
    try {
      return await this.request('/api/ai/overview');
    } catch (error) {
      if (!this.isNotFoundError(error)) {
        throw error;
      }

      const bot = await this.getBotStatus().catch(() => null);
      const nowIso = new Date().toISOString();

      return {
        status: 'degraded',
        source: 'fallback',
        lastInferenceAt: bot?.lastTradeTime || nowIso,
        model: {
          artifact: null,
          lastTrainedAt: null,
          datasetRows: 0,
          preferredUniverse: [],
        },
        learningPipeline: [
          {
            stage: 'AI endpoint',
            status: 'degraded',
            detail: 'Backend AI monitor endpoint is unavailable (404).',
          },
          {
            stage: 'Fallback telemetry',
            status: 'running',
            detail: 'Using bot status endpoint until AI monitor API is enabled.',
          },
        ],
        metrics: {
          activeTrades: Number(bot?.activeTrades || 0),
          winRate: Number(bot?.winRate || 0),
          warningEvents: 0,
          errorEvents: 0,
          processedEvents: 0,
        },
      };
    }
  }

  async getAIRegimeStatus() {
    try {
      return await this.request('/api/ai/regime');
    } catch (error) {
      if (this.isNotFoundError(error)) {
        return null;
      }
      throw error;
    }
  }

  async updateAIProfileMode(profile = 'auto') {
    const normalized = String(profile || 'auto').trim().toLowerCase();
    return this.updateUserSettings({ aiManualStrategyProfile: normalized || 'auto' });
  }

  async resetAIProfileOverride() {
    return this.request('/api/ai/profile/reset', {
      method: 'POST',
    });
  }

  async getAILogs(limit = 100) {
    try {
      return await this.request(`/api/ai/logs?limit=${limit}`);
    } catch (error) {
      if (this.isNotFoundError(error)) {
        return [];
      }
      throw error;
    }
  }

  async createAILog(payload) {
    try {
      return await this.request('/api/ai/logs', {
        method: 'POST',
        body: JSON.stringify(payload),
      });
    } catch (error) {
      if (this.isNotFoundError(error)) {
        return {
          id: `fallback-${Date.now()}`,
          level: payload?.level || 'info',
          eventType: payload?.eventType || 'manual',
          message: payload?.message || 'Fallback log (endpoint unavailable)',
          payload: payload?.payload || {},
          timestamp: new Date().toISOString(),
          source: 'fallback',
        };
      }
      throw error;
    }
  }

  // ============ Performance Reports API ============
  async getPerformanceReport(period = 'today') {
    return this.request(`/api/reports/performance?period=${period}`);
  }

  async generateReport(type, params = {}) {
    return this.request(`/api/reports/${type}`, {
      method: 'POST',
      body: JSON.stringify(params),
    });
  }
}

export default new ApiService();
