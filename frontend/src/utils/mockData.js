/**
 * Mock Data for Dashboard Development
 * Defines the ideal JSON shape for API responses
 * When backend is ready, just replace these functions with real API calls
 */

export const mockPortfolioData = {
  totalValue: 125000, // Total portfolio value in IDR
  totalP_L: 8750, // Profit/Loss
  percentP_L: 7.5, // Percentage gain
  cash: 45000, // Available cash
  purchasingPower: 112500, // Cash + margin available
  lastUpdate: new Date().toISOString(),
  positions: [
    {
      symbol: 'BBCA.JK',
      name: 'Bank Central Asia',
      quantity: 100,
      entryPrice: 450000,
      currentPrice: 465000,
      totalValue: 46500000,
      p_l: 1500000,
      percentP_L: 3.3,
      sector: 'Financial Services',
      riskScore: 'Low',
    },
    {
      symbol: 'BMRI.JK',
      name: 'Bank Mandiri',
      quantity: 150,
      entryPrice: 8200,
      currentPrice: 8650,
      totalValue: 1297500,
      p_l: 67500,
      percentP_L: 5.5,
      sector: 'Financial Services',
      riskScore: 'Low',
    },
    {
      symbol: 'ASII.JK',
      name: 'Astra International',
      quantity: 50,
      entryPrice: 9000,
      currentPrice: 9200,
      totalValue: 460000,
      p_l: 10000,
      percentP_L: 2.2,
      sector: 'Automotive',
      riskScore: 'Medium',
    },
    {
      symbol: 'TLKM.JK',
      name: 'Telekomunikasi Indonesia',
      quantity: 200,
      entryPrice: 3400,
      currentPrice: 3550,
      totalValue: 710000,
      p_l: 30000,
      percentP_L: 4.4,
      sector: 'Telecommunications',
      riskScore: 'Low',
    },
  ],
}

export const mockBotStatus = {
  status: 'running', // 'idle', 'running', 'paused', 'liquidating', 'maintenance'
  uptime: '14h 32m', // How long has been running
  activeTrades: 4, // Number of open positions
  totalTradesToday: 12,
  successfulTrades: 9,
  failedTrades: 3,
  winRate: 0.75, // 75%
  lastTradeTime: new Date(Date.now() - 15 * 60000).toISOString(), // 15 min ago
  nextAnalysisIn: '3m 45s', // Time until next signal check
  performanceToday: {
    totalP_L: 875000,
    percentP_L: 0.7,
  },
}

export const mockTopSignals = [
  {
    id: 1,
    symbol: 'INDF.JK',
    name: 'Indofood Sukses Makmur',
    signal: 'STRONG_BUY',
    confidence: 0.92, // 92% confidence
    reason: 'Volume spike 45% + Positive sentiment',
    predictedMove: '+3.2%', // Expected upside
    riskLevel: 'Low-Medium',
    sector: 'Consumer Goods',
    currentPrice: 9150,
    targetPrice: 9440,
    timestamp: new Date().toISOString(),
  },
  {
    id: 2,
    symbol: 'UNVR.JK',
    name: 'Unilever Indonesia',
    signal: 'BUY',
    confidence: 0.85,
    reason: 'RSI breakout + Institutional buying detected',
    predictedMove: '+2.1%',
    riskLevel: 'Low',
    sector: 'Consumer Goods',
    currentPrice: 2850,
    targetPrice: 2910,
    timestamp: new Date(Date.now() - 5 * 60000).toISOString(),
  },
  {
    id: 3,
    symbol: 'ANTM.JK',
    name: 'Antam',
    signal: 'HOLD',
    confidence: 0.68,
    reason: 'Mixed signals - awaiting breakout confirmation',
    predictedMove: '+0.8%',
    riskLevel: 'Medium',
    sector: 'Mining',
    currentPrice: 4200,
    targetPrice: 4435,
    timestamp: new Date(Date.now() - 30 * 60000).toISOString(),
  },
]

export const mockChartData = {
  symbol: 'BBCA.JK',
  timeframe: '1d', // 1m, 5m, 15m, 1h, 1d, 1w, 1mo
  data: [
    // Format: { time, open, high, low, close, volume }
    { time: '2026-03-25', open: 442000, high: 448000, low: 440000, close: 445000, volume: 1250000 },
    { time: '2026-03-26', open: 445000, high: 452000, low: 444000, close: 449000, volume: 1580000 },
    { time: '2026-03-27', open: 449000, high: 454000, low: 447000, close: 451000, volume: 1420000 },
    { time: '2026-03-28', open: 451000, high: 460000, low: 450000, close: 458000, volume: 2100000 }, // Volume spike
    { time: '2026-03-29', open: 458000, high: 462000, low: 456000, close: 460000, volume: 1680000 },
    { time: '2026-03-31', open: 460000, high: 467000, low: 459000, close: 465000, volume: 1950000 },
  ],
  annotations: [
    { time: '2026-03-28', text: 'Volume Spike +45%', color: '#00AA00' },
    { time: '2026-03-31', text: 'Breakout', color: '#0088FF' },
  ],
}

export const mockSectorHeatmap = [
  { name: 'Financial Services', value: 12.5, color: '#00DD00' }, // Green = positive
  { name: 'Consumer Goods', value: 8.2, color: '#00DD00' },
  { name: 'Telecommunications', value: 5.1, color: '#FFAA00' }, // Orange = neutral
  { name: 'Automotive', value: -2.3, color: '#FF5555' }, // Red = negative
  { name: 'Mining', value: -1.2, color: '#FF5555' },
  { name: 'Energy', value: 2.1, color: '#00DD00' },
  { name: 'Healthcare', value: 3.5, color: '#00DD00' },
  { name: 'Infrastructure', value: 1.8, color: '#FFAA00' },
]

export const mockMarketSentiment = {
  overallSentiment: 0.65, // -1 to 1, where 1 is bullish
  sentiment: 'BULLISH',
  score: 65, // 0-100
  sourceBreakdown: {
    newsAnalysis: 0.72,
    socialMedia: 0.58,
    technicalAnalysis: 0.68,
    institutionalFlow: 0.62,
  },
  recentNews: [
    {
      headline: 'BI Pertahankan Suku Bunga, Sinyal Positif untuk Pasar Modal',
      sentiment: 'positive',
      source: 'Reuters',
      timestamp: new Date(Date.now() - 2 * 3600000).toISOString(),
    },
    {
      headline: 'Pelaku Pasar Optimis dengan Kinerja IHSG Kuartal I 2026',
      sentiment: 'positive',
      source: 'Kontan',
      timestamp: new Date(Date.now() - 4 * 3600000).toISOString(),
    },
    {
      headline: 'Rupiah Stabil, Investor Asing Mulai Kembali ke BEI',
      sentiment: 'positive',
      source: 'Bisnis.com',
      timestamp: new Date(Date.now() - 6 * 3600000).toISOString(),
    },
  ],
}

export const mockPortfolioHealthScore = {
  score: 78, // 0-100
  rating: 'Good',
  factors: {
    diversification: 82,
    riskBalance: 75,
    profitability: 68,
    momentum: 81,
    volatility: 72,
  },
  recommendation: 'Portfolio is well-diversified with good momentum. Consider adding defensive positions before earnings season.',
}

export const mockRecentActivity = [
  {
    id: 1,
    type: 'BUY',
    symbol: 'INDF.JK',
    quantity: 50,
    price: 9100,
    timestamp: new Date(Date.now() - 15 * 60000).toISOString(),
    status: 'EXECUTED',
    signal: 'Volume spike + Momentum breakout',
  },
  {
    id: 2,
    type: 'BUY',
    symbol: 'UNVR.JK',
    quantity: 100,
    price: 2845,
    timestamp: new Date(Date.now() - 45 * 60000).toISOString(),
    status: 'EXECUTED',
    signal: 'RSI breakout from oversold',
  },
  {
    id: 3,
    type: 'SELL',
    symbol: 'BMRI.JK',
    quantity: 50,
    price: 8620,
    timestamp: new Date(Date.now() - 120 * 60000).toISOString(),
    status: 'EXECUTED',
    signal: 'Profit taking at resistance',
  },
  {
    id: 4,
    type: 'ANALYSIS',
    symbol: null,
    message: 'Market analysis updated: BULLISH bias maintained',
    timestamp: new Date(Date.now() - 180 * 60000).toISOString(),
    status: 'INFO',
  },
]

/**
 * Simulate real-time data updates
 * In production, replace with WebSocket connection to backend
 */
export function getRealtimePortfolioUpdate() {
  const variance = (Math.random() - 0.5) * 0.02 // ±1% variance
  return {
    ...mockPortfolioData,
    totalValue: Math.round(mockPortfolioData.totalValue * (1 + variance)),
    totalP_L: Math.round(mockPortfolioData.totalP_L * (1 + variance)),
    lastUpdate: new Date().toISOString(),
  }
}

export function getRealtimeBotStatus() {
  return {
    ...mockBotStatus,
    lastUpdate: new Date().toISOString(),
  }
}
