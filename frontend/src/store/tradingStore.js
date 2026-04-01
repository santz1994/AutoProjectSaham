import create from 'zustand'

/**
 * Global Trading State Management
 * Manages: Bot status, Kill Switch, Trading activity
 * Kill Switch (Emergency Stop) affects ALL trading components instantly
 */
export const useTradingStore = create((set) => ({
  // ============ Kill Switch (Emergency Stop) ============
  isTradingActive: true,        // True = trading enabled, False = all trading halted
  killSwitchTriggered: false,   // True = user hit emergency stop
  lastKillSwitchTime: null,

  toggleKillSwitch: () => set((state) => ({
    killSwitchTriggered: !state.killSwitchTriggered,
    isTradingActive: state.killSwitchTriggered, // Flip the state
    lastKillSwitchTime: new Date().toISOString(),
  })),

  activateKillSwitch: () => set({
    killSwitchTriggered: true,
    isTradingActive: false,
    lastKillSwitchTime: new Date().toISOString(),
  }),

  deactivateKillSwitch: () => set({
    killSwitchTriggered: false,
    isTradingActive: true,
    lastKillSwitchTime: new Date().toISOString(),
  }),

  // ============ Bot Status ============
  botStatus: 'idle', // 'idle', 'running', 'paused', 'liquidating', 'maintenance'
  setBotStatus: (status) => set({ botStatus: status }),

  // ============ Portfolio Data ============
  portfolio: {
    totalValue: 0,
    totalP_L: 0,
    percentP_L: 0,
    cash: 0,
    positions: [],
    lastUpdate: null,
  },
  setPortfolio: (portfolio) => set({ portfolio, 'portfolio.lastUpdate': new Date().toISOString() }),

  // ============ Market Data ============
  latestPrice: 0,
  marketSentiment: 0, // -1 to 1, where 1 is most bullish
  setMarketData: (price, sentiment) => set({ latestPrice: price, marketSentiment: sentiment }),

  // ============ AI Signals ============
  topSignals: [],
  setTopSignals: (signals) => set({ topSignals: signals }),

  // ============ Health Score ============
  portfolioHealthScore: 70, // 0-100 scale
  setPortfolioHealthScore: (score) => set({ portfolioHealthScore: Math.max(0, Math.min(100, score)) }),
}))

export default useTradingStore
