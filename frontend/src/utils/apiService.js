/**
 * API Service - Real Backend Integration
 * Replaces all mock data with actual API calls
 */

import { getAPIBase } from './authService';

class ApiService {
  constructor() {
    this.baseURL = getAPIBase();
  }

  // Helper method for API calls with error handling
  async request(endpoint, options = {}) {
    const url = `${this.baseURL}${endpoint}`;
    const defaultOptions = {
      credentials: 'include', // Include cookies for auth
      headers: {
        'Content-Type': 'application/json',
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
  async getNotifications(unreadOnly = false) {
    return this.request(`/api/notifications${unreadOnly ? '?unread=true' : ''}`);
  }

  async markNotificationRead(id) {
    return this.request(`/api/notifications/${id}/read`, { method: 'POST' });
  }

  async markAllNotificationsRead() {
    return this.request('/api/notifications/read-all', { method: 'POST' });
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
