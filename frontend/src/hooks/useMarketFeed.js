/**
 * useMarketFeed.js — Real-time WebSocket hook for live market data.
 *
 * Phase 6.2/8.5: Connects to Binance/Bybit WebSocket for real-time candle
 * and ticker streaming. Returns live price, OHLCV candles, and connection status.
 *
 * Usage:
 *   const { lastPrice, candles, connected, error } = useMarketFeed('BTC/USDT', '1m');
 */
import { useState, useEffect, useRef, useCallback } from 'react';

const DEFAULT_WS_URL = import.meta.env.VITE_WS_MARKET_URL || 'ws://localhost:8000/ws/charts';

// Binance public WebSocket for direct streaming (no auth needed)
const BINANCE_WS_BASE = 'wss://stream.binance.com:9443/ws';

/**
 * Convert symbol like 'BTC/USDT' → 'btcusdt' for Binance WS
 */
function toBinanceStream(symbol = 'BTC/USDT') {
  return symbol.replace('/', '').toLowerCase();
}

/**
 * Convert timeframe like '5m', '1h', '1d' → Binance kline interval
 */
function toBinanceInterval(tf = '5m') {
  const map = {
    '1m': '1m', '3m': '3m', '5m': '5m', '15m': '15m', '30m': '30m',
    '1h': '1h', '2h': '2h', '4h': '4h', '6h': '6h', '8h': '8h', '12h': '12h',
    '1d': '1d', '3d': '3d', '1w': '1w', '1M': '1M',
  };
  return map[tf] || '5m';
}

/**
 * Hook for real-time market feed via WebSocket.
 *
 * Priority:
 * 1. Backend WebSocket (if authenticated, proxied through nginx)
 * 2. Direct Binance public WebSocket (fallback, no auth needed)
 *
 * @param {string} symbol - Trading pair, e.g. 'BTC/USDT'
 * @param {string} timeframe - Candle interval, e.g. '5m', '1h'
 * @param {object} options
 * @param {boolean} options.useBackend - If true, connect to backend WS (default: false for direct Binance)
 * @param {number} options.maxCandles - Max candles to keep in buffer (default: 500)
 * @returns {{ lastPrice, lastCandle, candles, ticker, connected, connecting, error, reconnect }}
 */
export default function useMarketFeed(
  symbol = 'BTC/USDT',
  timeframe = '5m',
  options = {}
) {
  const {
    useBackend = false,
    maxCandles = 500,
  } = options;

  const [lastPrice, setLastPrice] = useState(null);
  const [lastCandle, setLastCandle] = useState(null);
  const [candles, setCandles] = useState([]);
  const [ticker, setTicker] = useState(null);
  const [connected, setConnected] = useState(false);
  const [connecting, setConnecting] = useState(false);
  const [error, setError] = useState(null);

  const wsRef = useRef(null);
  const reconnectTimer = useRef(null);
  const reconnectAttempt = useRef(0);
  const maxReconnectAttempts = 20;
  const mountedRef = useRef(true);

  // Stable refs for cleanup
  const symbolRef = useRef(symbol);
  const timeframeRef = useRef(timeframe);
  symbolRef.current = symbol;
  timeframeRef.current = timeframe;

  const cleanup = useCallback(() => {
    if (reconnectTimer.current) {
      clearTimeout(reconnectTimer.current);
      reconnectTimer.current = null;
    }
    if (wsRef.current) {
      try { wsRef.current.close(); } catch (_) { /* ignore */ }
      wsRef.current = null;
    }
  }, []);

  const connect = useCallback(() => {
    cleanup();
    if (!mountedRef.current) return;

    setConnecting(true);
    setError(null);

    let wsUrl;
    let parseMessage;

    if (useBackend) {
      // Connect to backend WebSocket proxy
      const token = localStorage.getItem('auth_token') || '';
      wsUrl = `${DEFAULT_WS_URL}?token=${encodeURIComponent(token)}`;
      parseMessage = (data) => {
        try {
          const msg = JSON.parse(data);
          if (msg.type === 'candle' || msg.type === 'kline') {
            return { type: 'candle', candle: msg.data || msg };
          }
          if (msg.type === 'ticker') {
            return { type: 'ticker', ticker: msg.data || msg };
          }
          if (msg.last_price !== undefined) {
            return { type: 'price', price: parseFloat(msg.last_price) };
          }
          return { type: 'unknown', raw: msg };
        } catch {
          return null;
        }
      };
    } else {
      // Direct Binance public WebSocket
      const stream = toBinanceStream(symbolRef.current);
      const interval = toBinanceInterval(timeframeRef.current);
      wsUrl = `${BINANCE_WS_BASE}/${stream}@kline_${interval}`;
      parseMessage = (data) => {
        try {
          const msg = JSON.parse(data);
          if (msg.e === 'kline') {
            const k = msg.k;
            const candle = {
              time: Math.floor(k.t / 1000),  // seconds for lightweight-charts
              open: parseFloat(k.o),
              high: parseFloat(k.h),
              low: parseFloat(k.l),
              close: parseFloat(k.c),
              volume: parseFloat(k.v),
              isClosed: k.x,
            };
            return { type: 'candle', candle };
          }
          if (msg.e === '24hrTicker') {
            return {
              type: 'ticker',
              ticker: {
                priceChange: parseFloat(msg.p),
                priceChangePercent: parseFloat(msg.P),
                lastPrice: parseFloat(msg.c),
                highPrice: parseFloat(msg.h),
                lowPrice: parseFloat(msg.l),
                volume: parseFloat(msg.v),
                quoteVolume: parseFloat(msg.q),
              },
            };
          }
          return null;
        } catch {
          return null;
        }
      };
    }

    try {
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        if (!mountedRef.current) return;
        setConnected(true);
        setConnecting(false);
        setError(null);
        reconnectAttempt.current = 0;
      };

      ws.onmessage = (evt) => {
        if (!mountedRef.current) return;
        const parsed = parseMessage(evt.data);
        if (!parsed) return;

        if (parsed.type === 'candle') {
          const c = parsed.candle;
          setLastCandle(c);
          if (c.close !== undefined) setLastPrice(c.close);

          setCandles((prev) => {
            const updated = [...prev];
            // Update last candle if same time, else append
            if (updated.length > 0 && updated[updated.length - 1].time === c.time) {
              updated[updated.length - 1] = c;
            } else {
              updated.push(c);
            }
            // Trim to maxCandles
            if (updated.length > maxCandles) {
              return updated.slice(updated.length - maxCandles);
            }
            return updated;
          });
        }

        if (parsed.type === 'ticker') {
          setTicker(parsed.ticker);
          if (parsed.ticker.lastPrice) setLastPrice(parsed.ticker.lastPrice);
        }

        if (parsed.type === 'price') {
          setLastPrice(parsed.price);
        }
      };

      ws.onerror = (err) => {
        if (!mountedRef.current) return;
        setError('WebSocket connection error');
        setConnecting(false);
      };

      ws.onclose = (evt) => {
        if (!mountedRef.current) return;
        setConnected(false);
        setConnecting(false);

        // Auto-reconnect with exponential backoff
        if (reconnectAttempt.current < maxReconnectAttempts) {
          const delay = Math.min(1000 * Math.pow(1.5, reconnectAttempt.current), 30000);
          reconnectAttempt.current += 1;
          reconnectTimer.current = setTimeout(() => {
            if (mountedRef.current) connect();
          }, delay);
        } else {
          setError('Max reconnect attempts reached. Click reconnect to retry.');
        }
      };
    } catch (err) {
      setError(`Failed to connect: ${err.message}`);
      setConnecting(false);
    }
  }, [useBackend, maxCandles, cleanup]);

  const reconnect = useCallback(() => {
    reconnectAttempt.current = 0;
    setError(null);
    connect();
  }, [connect]);

  // Connect on mount or when symbol/timeframe changes
  useEffect(() => {
    mountedRef.current = true;
    setCandles([]); // Reset candles on symbol/tf change
    setLastPrice(null);
    setTicker(null);
    connect();

    return () => {
      mountedRef.current = false;
      cleanup();
    };
  }, [symbol, timeframe, connect, cleanup]);

  return {
    lastPrice,
    lastCandle,
    candles,
    ticker,
    connected,
    connecting,
    error,
    reconnect,
  };
}