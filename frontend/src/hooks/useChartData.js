/**
 * useChartData Hook
 * =================
 * 
 * Custom hook for managing chart data and WebSocket connections.
 * Handles:
 * - Fetching OHLCV data
 * - WebSocket real-time updates
 * - Timeframe changes
 * - Error handling
 * 
 * Author: AutoSaham Team
 * Version: 1.0.0
 */

import { useState, useEffect, useCallback, useRef } from 'react';

const useChartData = (symbol, initialTimeframe = '1d') => {
  const [chartData, setChartData] = useState({
    metadata: null,
    candles: [],
  });
  const [timeframe, setTimeframeState] = useState(initialTimeframe);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [isConnected, setIsConnected] = useState(false);
  const wsRef = useRef(null);
  const wsTimeoutRef = useRef(null);

  // Fetch initial chart data
  const fetchChartData = useCallback(async () => {
    if (!symbol) return;

    setLoading(true);
    setError(null);

    try {
      // Fetch metadata
      const metadataRes = await fetch(`/api/charts/metadata/${symbol}`);
      if (!metadataRes.ok) {
        throw new Error(`Metadata fetch failed: ${metadataRes.statusText}`);
      }
      const metadata = await metadataRes.json();

      // Fetch candles
      const candlesRes = await fetch(
        `/api/charts/candles/${symbol}?timeframe=${timeframe}&limit=100`
      );
      if (!candlesRes.ok) {
        throw new Error(`Candles fetch failed: ${candlesRes.statusText}`);
      }
      const { candles } = await candlesRes.json();

      setChartData({
        metadata,
        candles: candles || [],
      });
    } catch (err) {
      setError(err.message);
      console.error('Chart data fetch error:', err);
    } finally {
      setLoading(false);
    }
  }, [symbol, timeframe]);

  // Connect to WebSocket for real-time updates
  const connectWebSocket = useCallback(async () => {
    if (!symbol) return;

    const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${wsProtocol}//${window.location.host}/ws/charts/${symbol}`;

    try {
      const ws = new WebSocket(wsUrl);

      ws.onopen = () => {
        console.log(`Chart WebSocket connected: ${symbol}`);
        setIsConnected(true);
        wsRef.current = ws;

        // Keep-alive ping every 30 seconds
        const pingInterval = setInterval(() => {
          if (ws.readyState === WebSocket.OPEN) {
            ws.send('ping');
          }
        }, 30000);

        ws.pingInterval = pingInterval;
      };

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);

          if (data.type === 'candle_update') {
            // Update last candle
            setChartData((prev) => ({
              ...prev,
              candles: prev.candles.map((c) =>
                c.time === data.candle.time ? data.candle : c
              ),
            }));
          } else {
            // Initial or full data refresh
            setChartData({
              metadata: data.metadata || chartData.metadata,
              candles: data.candles || [],
            });
          }
        } catch (err) {
          console.error('WebSocket message error:', err);
        }
      };

      ws.onerror = (err) => {
        console.error('WebSocket error:', err);
        setError('WebSocket connection error');
      };

      ws.onclose = () => {
        console.log(`Chart WebSocket disconnected: ${symbol}`);
        setIsConnected(false);
        clearInterval(ws.pingInterval);

        // Attempt to reconnect after 3 seconds
        wsTimeoutRef.current = setTimeout(() => {
          connectWebSocket();
        }, 3000);
      };

      wsRef.current = ws;
    } catch (err) {
      setError(`WebSocket connection failed: ${err.message}`);
      console.error('WebSocket connection error:', err);
    }
  }, [symbol, chartData.metadata]);

  // Fetch initial data
  useEffect(() => {
    fetchChartData();
  }, [fetchChartData]);

  // Connect to WebSocket
  useEffect(() => {
    connectWebSocket();

    return () => {
      if (wsRef.current) {
        wsRef.current.close();
      }
      if (wsTimeoutRef.current) {
        clearTimeout(wsTimeoutRef.current);
      }
    };
  }, [connectWebSocket]);

  // Change timeframe
  const changeTimeframe = useCallback(
    (newTimeframe) => {
      setTimeframeState(newTimeframe);
    },
    []
  );

  // Refresh data manually
  const refresh = useCallback(() => {
    fetchChartData();
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send('update');
    }
  }, [fetchChartData]);

  return {
    metadata: chartData.metadata,
    candles: chartData.candles,
    timeframe,
    changeTimeframe,
    loading,
    error,
    isConnected,
    refresh,
  };
};

export default useChartData;
