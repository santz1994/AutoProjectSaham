import { useTradingStore, type Marker } from '../store/useTradingStore'

const MAX_CANDLES = 500
const MAX_MARKERS = 200
const TICK_FLUSH_MS = 250
const ORDERBOOK_FLUSH_MS = 120
const MARKER_FLUSH_MS = 250

function emitMarketFeedStatus(status: 'connected' | 'disconnected', reason = '') {
  try {
    window.dispatchEvent(new CustomEvent('autosaham:market-feed-status', {
      detail: {
        status,
        reason,
        timestamp: new Date().toISOString(),
      },
    }))
  } catch {
    // Ignore event dispatch issues to keep feed loop resilient.
  }
}

function toSec(t: any) {
  try {
    if (typeof t === 'number') {
      if (t > 1e12) return Math.floor(t / 1000)
      return Math.floor(t)
    }
    const n = Date.parse(String(t))
    if (!isNaN(n)) return Math.floor(n / 1000)
  } catch {
    // Fallback below
  }
  return Math.floor(Date.now() / 1000)
}

export default function startMarketFeed() {
  const updateCandles = useTradingStore.getState().updateCandles
  const updateOrderBook = useTradingStore.getState().updateOrderBook
  const updateMarkers = useTradingStore.getState().updateMarkers

  let tickQueue: Array<{ bucket: number; price: number }> = []
  let tickFlushHandle: number | null = null

  let pendingOrderBook: { bids: Array<{ price: number; volume: number }>; asks: Array<{ price: number; volume: number }> } | null = null
  let orderBookFlushHandle: number | null = null

  let markerQueue: Marker[] = []
  let markerFlushHandle: number | null = null

  const flushTicks = () => {
    tickFlushHandle = null
    if (tickQueue.length === 0) return

    const state = useTradingStore.getState()
    const candles = Array.isArray(state.candles) ? [...state.candles] : []

    for (const tick of tickQueue) {
      const last = candles.length ? { ...candles[candles.length - 1] } : null
      if (!last || Number(last.time) < tick.bucket) {
        candles.push({
          time: tick.bucket,
          open: tick.price,
          high: tick.price,
          low: tick.price,
          close: tick.price,
        })
        continue
      }

      if (Number(last.time) === tick.bucket) {
        last.high = Math.max(Number(last.high), tick.price)
        last.low = Math.min(Number(last.low), tick.price)
        last.close = tick.price
        candles[candles.length - 1] = last
      }
    }

    tickQueue = []
    updateCandles(candles.slice(-MAX_CANDLES))
  }

  const scheduleTickFlush = () => {
    if (tickFlushHandle !== null) return
    tickFlushHandle = window.setTimeout(flushTicks, TICK_FLUSH_MS)
  }

  const flushOrderBook = () => {
    orderBookFlushHandle = null
    if (!pendingOrderBook) return

    updateOrderBook(pendingOrderBook.bids, pendingOrderBook.asks)
    pendingOrderBook = null
  }

  const scheduleOrderBookFlush = () => {
    if (orderBookFlushHandle !== null) return
    orderBookFlushHandle = window.setTimeout(flushOrderBook, ORDERBOOK_FLUSH_MS)
  }

  const flushMarkers = () => {
    markerFlushHandle = null
    if (markerQueue.length === 0) return

    const queuedNewestFirst = markerQueue.slice().reverse()
    const state = useTradingStore.getState()
    const next = Array.isArray(state.markers)
      ? [...queuedNewestFirst, ...state.markers].slice(0, MAX_MARKERS)
      : queuedNewestFirst.slice(0, MAX_MARKERS)

    markerQueue = []
    updateMarkers(next)
  }

  const scheduleMarkerFlush = () => {
    if (markerFlushHandle !== null) return
    markerFlushHandle = window.setTimeout(flushMarkers, MARKER_FLUSH_MS)
  }

  const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
  const envApiUrl = (import.meta as any)?.env?.VITE_API_URL as string | undefined

  let backendHost = window.location.host
  if (envApiUrl) {
    try {
      backendHost = new URL(envApiUrl).host
    } catch {
      backendHost = window.location.host
    }
  } else if (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1') {
    backendHost = 'localhost:8000'
  }

  const wsUrl = `${proto}://${backendHost}/ws/events`
  const ws = new WebSocket(wsUrl)

  ws.onopen = () => {
    emitMarketFeedStatus('connected')
  }

  ws.onmessage = (event) => {
    let ev: any = null

    try {
      ev = JSON.parse(event.data)
    } catch {
      return
    }

    if (!ev || typeof ev !== 'object') return

    try {
      const t = ev.type || ev.event || ev.event_type

      if (t === 'tick' || t === 'price_tick') {
        const price = Number(ev.price || ev.last || ev.p || 0)
        if (!price) return

        const ts = toSec(ev.time || ev.ts || ev.t)
        const bucket = Math.floor(ts / 60) * 60

        tickQueue.push({ bucket, price })
        scheduleTickFlush()
        return
      }

      if (t === 'order_book' || t === 'book' || t === 'orderbook') {
        const bids = Array.isArray(ev.bids)
          ? ev.bids.map((b: any) => ({ price: Number(b.price), volume: Number(b.volume) }))
          : []
        const asks = Array.isArray(ev.asks)
          ? ev.asks.map((a: any) => ({ price: Number(a.price), volume: Number(a.volume) }))
          : []

        pendingOrderBook = { bids, asks }
        scheduleOrderBookFlush()
        return
      }

      if (t === 'order_filled' || t === 'trade' || t === 'fill') {
        const trade = ev.trade || ev
        const price = Number(trade.price || trade.p || 0)
        const side = (trade.side || trade.direction || '').toLowerCase()
        const ts = toSec(trade.time || trade.ts || trade.t || ev.time || ev.ts)

        const marker: Marker = {
          time: ts,
          position: side === 'sell' ? 'aboveBar' : 'belowBar',
          color: side === 'sell' ? '#FF9800' : '#2196F3',
          shape: side === 'sell' ? 'arrowDown' : 'arrowUp',
          text: `${(trade.symbol || '')} ${side.toUpperCase()} @ ${price}`,
        }

        markerQueue.push(marker)
        scheduleMarkerFlush()
      }
    } catch {
      // Ignore malformed event payloads
    }
  }

  ws.onerror = () => {
    emitMarketFeedStatus('disconnected', 'websocket_error')
    // Keep silent here; app pages should continue without market feed.
  }

  ws.onclose = () => {
    emitMarketFeedStatus('disconnected', 'websocket_closed')
  }

  return () => {
    if (tickFlushHandle !== null) {
      window.clearTimeout(tickFlushHandle)
      tickFlushHandle = null
    }
    if (orderBookFlushHandle !== null) {
      window.clearTimeout(orderBookFlushHandle)
      orderBookFlushHandle = null
    }
    if (markerFlushHandle !== null) {
      window.clearTimeout(markerFlushHandle)
      markerFlushHandle = null
    }

    flushTicks()
    flushOrderBook()
    flushMarkers()

    try {
      ws.close()
    } catch {
      // Ignore close failures
    }

    emitMarketFeedStatus('disconnected', 'feed_stopped')
  }
}
