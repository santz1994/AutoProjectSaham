import { useEffect } from 'react'
import useWebSocket from './useWebSocket'
import { useTradingStore, type Marker } from '../store/useTradingStore'

function toSec(t: any) {
  try {
    if (typeof t === 'number') {
      // treat as ms when obviously large
      if (t > 1e12) return Math.floor(t / 1000)
      return Math.floor(t)
    }
    const n = Date.parse(String(t))
    if (!isNaN(n)) return Math.floor(n / 1000)
  } catch {}
  return Math.floor(Date.now() / 1000)
}

export default function useMarketFeed() {
  const updateCandles = useTradingStore.getState().updateCandles
  const updateOrderBook = useTradingStore.getState().updateOrderBook
  const updateMarkers = useTradingStore.getState().updateMarkers

  useWebSocket('/ws/events', (ev) => {
    if (!ev || typeof ev !== 'object') return

    try {
      const t = ev.type || ev.event || ev.event_type

      // price tick event: expected { type: 'tick', symbol, price, volume, time }
      if (t === 'tick' || t === 'price_tick') {
        const price = Number(ev.price || ev.last || ev.p || 0)
        if (!price) return
        const ts = toSec(ev.time || ev.ts || ev.t)

        // simple minute-aggregation: read current candles and update last or append
        const state = useTradingStore.getState()
        const cur = Array.isArray(state.candles) ? [...state.candles] : []
        const last = cur.length ? { ...cur[cur.length - 1] } : null
        const bucket = Math.floor(ts / 60) * 60
        if (!last || Number(last.time) < bucket) {
          cur.push({ time: bucket, open: price, high: price, low: price, close: price })
        } else {
          last.high = Math.max(last.high, price)
          last.low = Math.min(last.low, price)
          last.close = price
          cur[cur.length - 1] = last
        }
        updateCandles(cur.slice(-500))
        return
      }

      // order book update: { type: 'order_book', bids: [{price,volume}], asks: [...] }
      if (t === 'order_book' || t === 'book' || t === 'orderbook') {
        const bids = Array.isArray(ev.bids) ? ev.bids.map((b: any) => ({ price: Number(b.price), volume: Number(b.volume) })) : []
        const asks = Array.isArray(ev.asks) ? ev.asks.map((a: any) => ({ price: Number(a.price), volume: Number(a.volume) })) : []
        updateOrderBook(bids, asks)
        return
      }

      // filled order -> add marker
      if (t === 'order_filled' || t === 'trade' || t === 'fill') {
        const trade = ev.trade || ev
        const price = Number(trade.price || trade.p || 0)
        const side = (trade.side || trade.direction || '').toLowerCase()
        const ts = toSec(trade.time || trade.ts || trade.t || ev.time || ev.ts)
        const m: Marker = {
          time: ts,
          position: side === 'sell' ? 'aboveBar' : 'belowBar',
          color: side === 'sell' ? '#FF9800' : '#2196F3',
          shape: side === 'sell' ? 'arrowDown' : 'arrowUp',
          text: `${(trade.symbol || '')} ${side.toUpperCase()} @ ${price}`,
        }
        const state = useTradingStore.getState()
        const markers = Array.isArray(state.markers) ? [m, ...state.markers].slice(0, 200) : [m]
        updateMarkers(markers)
        return
      }

      // other events: ignore or could be passed to UI event list
    } catch (err) {
      // ignore parsing errors
    }
  })
}
