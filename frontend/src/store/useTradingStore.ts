import create from 'zustand'

export type Candle = { time: string | number; open: number; high: number; low: number; close: number; volume?: number }
export type OrderBookItem = { price: number; volume: number }
export type Marker = { time: string | number; position?: 'aboveBar' | 'belowBar'; color?: string; shape?: string; text?: string }

interface TradingState {
  candles: Candle[]
  orderBook: { bids: OrderBookItem[]; asks: OrderBookItem[] }
  markers: Marker[]
  updateCandles: (c: Candle[]) => void
  updateOrderBook: (bids: OrderBookItem[], asks: OrderBookItem[]) => void
  updateMarkers: (m: Marker[]) => void
}

export const useTradingStore = create<TradingState>((set) => ({
  candles: [],
  orderBook: { bids: [], asks: [] },
  markers: [],
  updateCandles: (c) => set({ candles: c }),
  updateOrderBook: (bids, asks) => set({ orderBook: { bids, asks } }),
  updateMarkers: (m) => set({ markers: m }),
}))
