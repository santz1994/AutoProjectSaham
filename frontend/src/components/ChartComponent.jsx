/**
 * TradingView Chart Component
 * ============================
 * 
 * Lightweight-charts integration for IDX symbol viewing.
 * Features:
 * - Real-time WebSocket updates
 * - Jakarta timezone support
 * - IDX compliance (symbols, currency, trading hours)
 * - Multiple timeframes (1m, 5m, 15m, 30m, 1h, 4h, 1d, 1w, 1mo)
 * - Interactive candlestick chart
 * 
 * Author: AutoSaham Team
 * Version: 1.0.0
 */

import React, { useEffect, useRef, useState, useCallback, useMemo } from 'react';
import { createChart, ColorType } from 'lightweight-charts';
import useResponsive from '../hooks/useResponsive';
import { getAPIBase, getWebSocketBase } from '../utils/authService';
import './ChartComponent.css';

const DEFAULT_TIMEFRAMES = ['1m', '5m', '15m', '30m', '1h', '4h', '1d', '1w', '1mo'];

const THEME_COLORS = {
  dark: {
    background: '#131722',
    textColor: '#d1d5db',
    gridColor: '#2c2c2c',
    upColor: '#26a69a',
    downColor: '#f23645',
    borderUpColor: '#26a69a',
    borderDownColor: '#f23645',
  },
  light: {
    background: '#ffffff',
    textColor: '#262626',
    gridColor: '#f0f0f0',
    upColor: '#26a69a',
    downColor: '#f23645',
    borderUpColor: '#26a69a',
    borderDownColor: '#f23645',
  },
};

const ChartComponent = ({ symbol = 'BBCA.JK', timeframe = '1d', onTimeframeChange, theme = 'dark' }) => {
  const containerRef = useRef(null);
  const chartRef = useRef(null);
  const candleSeriesRef = useRef(null);
  const resizeObserverRef = useRef(null);
  const pendingCandlesRef = useRef(null);
  const latestCandleRef = useRef(null);
  const initialThemeRef = useRef(THEME_COLORS[theme] || THEME_COLORS.dark);
  const { isMobile, isTablet, viewport } = useResponsive();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [metadata, setMetadata] = useState(null);
  const [timeframes, setTimeframes] = useState(DEFAULT_TIMEFRAMES);
  const [isTrading, setIsTrading] = useState(false);
  const [lastUpdate, setLastUpdate] = useState(null);
  const [wsWarning, setWsWarning] = useState(null);

  const chartColors = useMemo(() => THEME_COLORS[theme] || THEME_COLORS.dark, [theme]);

  // Format timestamp to readable date
  const formatDate = useCallback((timestamp) => {
    return new Date(timestamp * 1000).toLocaleString('id-ID', {
      timeZone: 'Asia/Jakarta',
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    });
  }, []);

  const calculateChartHeight = useCallback(() => {
    const currentHeight = typeof window !== 'undefined' ? window.innerHeight : 768;
    const currentWidth = typeof window !== 'undefined' ? window.innerWidth : 1024;

    if (currentWidth < 768) return Math.min(currentHeight * 0.6, 400);
    if (currentWidth < 1024) return Math.min(currentHeight * 0.65, 500);
    return 600;
  }, []);

  const applyChartDimensions = useCallback(() => {
    if (!chartRef.current || !containerRef.current) {
      return;
    }

    const width = containerRef.current.clientWidth;
    if (!width || width < 100) {
      return;
    }

    const compactView = (typeof window !== 'undefined' ? window.innerWidth : 1024) < 768;

    chartRef.current.applyOptions({
      width,
      height: calculateChartHeight(),
      timeScale: {
        timeVisible: true,
        secondsVisible: !compactView,
        rightOffset: compactView ? 10 : 40,
      },
    });
  }, [calculateChartHeight]);

  // Initialize chart only once to avoid stacking chart instances.
  useEffect(() => {
    if (!containerRef.current || chartRef.current) {
      return undefined;
    }

    let disposed = false;
    let resizeTimer = null;

    const initChart = () => {
      if (disposed || chartRef.current || !containerRef.current) {
        return;
      }

      const width = containerRef.current.clientWidth;
      if (!width || width < 100) {
        return;
      }

      const compactView = (typeof window !== 'undefined' ? window.innerWidth : 1024) < 768;
      const seedTheme = initialThemeRef.current;

      try {
        const chart = createChart(containerRef.current, {
          layout: {
            background: { color: seedTheme.background, type: ColorType.Solid },
            textColor: seedTheme.textColor,
          },
          width,
          height: calculateChartHeight(),
          timeScale: {
            timeVisible: true,
            secondsVisible: !compactView,
            rightOffset: compactView ? 10 : 40,
          },
          localization: {
            locale: 'id-ID',
            timeFormatter: (timestamp) => {
              const date = new Date(timestamp * 1000);
              return date.toLocaleString('id-ID', {
                timeZone: 'Asia/Jakarta',
                month: '2-digit',
                day: '2-digit',
                hour: '2-digit',
                minute: compactView ? undefined : '2-digit',
              });
            },
          },
        });

        const candleSeries = chart.addCandlestickSeries({
          upColor: seedTheme.upColor,
          downColor: seedTheme.downColor,
          borderUpColor: seedTheme.borderUpColor,
          borderDownColor: seedTheme.borderDownColor,
          wickUpColor: seedTheme.upColor,
          wickDownColor: seedTheme.downColor,
        });

        chartRef.current = chart;
        candleSeriesRef.current = candleSeries;

        if (Array.isArray(pendingCandlesRef.current) && pendingCandlesRef.current.length > 0) {
          candleSeriesRef.current.setData(pendingCandlesRef.current);
          chartRef.current.timeScale().fitContent();
        }

        if (latestCandleRef.current) {
          candleSeriesRef.current.update(latestCandleRef.current);
        }

        if (typeof window !== 'undefined') {
          const currentCount = Number(window.__AUTOSAHAM_CHART_INSTANCE_COUNT || 0);
          window.__AUTOSAHAM_CHART_INSTANCE_COUNT = currentCount + 1;
        }
      } catch (err) {
        setError(`Failed to initialize chart: ${err.message}`);
        console.error('Chart initialization error:', err);
      }
    };

    const handleResize = () => {
      clearTimeout(resizeTimer);
      resizeTimer = setTimeout(() => {
        if (chartRef.current) {
          applyChartDimensions();
          return;
        }

        initChart();
      }, 120);
    };

    initChart();

    if (typeof ResizeObserver !== 'undefined' && containerRef.current) {
      resizeObserverRef.current = new ResizeObserver(() => {
        if (chartRef.current) {
          applyChartDimensions();
          return;
        }

        initChart();
      });

      resizeObserverRef.current.observe(containerRef.current);
    }

    if (typeof window !== 'undefined') {
      window.addEventListener('resize', handleResize);
    }

    return () => {
      disposed = true;

      if (typeof window !== 'undefined') {
        window.removeEventListener('resize', handleResize);
      }

      clearTimeout(resizeTimer);

      if (resizeObserverRef.current) {
        resizeObserverRef.current.disconnect();
        resizeObserverRef.current = null;
      }

      if (chartRef.current) {
        chartRef.current.remove();
        chartRef.current = null;
        candleSeriesRef.current = null;

        if (typeof window !== 'undefined') {
          const currentCount = Number(window.__AUTOSAHAM_CHART_INSTANCE_COUNT || 1);
          window.__AUTOSAHAM_CHART_INSTANCE_COUNT = Math.max(currentCount - 1, 0);
        }
      }
    };
  }, [applyChartDimensions, calculateChartHeight]);

  // Apply theme updates without re-creating chart instance.
  useEffect(() => {
    if (!chartRef.current || !candleSeriesRef.current) {
      return;
    }

    chartRef.current.applyOptions({
      layout: {
        background: { color: chartColors.background, type: ColorType.Solid },
        textColor: chartColors.textColor,
      },
    });

    candleSeriesRef.current.applyOptions({
      upColor: chartColors.upColor,
      downColor: chartColors.downColor,
      borderUpColor: chartColors.borderUpColor,
      borderDownColor: chartColors.borderDownColor,
      wickUpColor: chartColors.upColor,
      wickDownColor: chartColors.downColor,
    });
  }, [chartColors]);

  useEffect(() => {
    applyChartDimensions();
  }, [applyChartDimensions, isMobile, isTablet, viewport.height, viewport.width]);

  useEffect(() => {
    const fetchSupportedTimeframes = async () => {
      try {
        const res = await fetch(`${getAPIBase()}/api/charts/timeframes`);
        if (!res.ok) {
          return;
        }
        const payload = await res.json();
        const fromApi = Array.isArray(payload?.timeframes) ? payload.timeframes : [];
        if (fromApi.length > 0) {
          setTimeframes(fromApi);
        }
      } catch (err) {
        console.warn('Using default chart timeframes:', err);
      }
    };

    fetchSupportedTimeframes();
  }, []);

  // Fetch initial chart data
  useEffect(() => {
    const fetchChartData = async () => {
      setLoading(true);
      setError(null);

      try {
        // Get metadata
        const metadataRes = await fetch(`${getAPIBase()}/api/charts/metadata/${symbol}`);
        if (!metadataRes.ok) {
          throw new Error(`Failed to fetch metadata: ${metadataRes.statusText}`);
        }
        const metadataData = await metadataRes.json();
        setMetadata(metadataData);

        // Get candles
        const candlesRes = await fetch(
          `${getAPIBase()}/api/charts/candles/${symbol}?timeframe=${timeframe}&limit=100`
        );
        if (!candlesRes.ok) {
          throw new Error(`Failed to fetch candles: ${candlesRes.statusText}`);
        }
        const candlesData = await candlesRes.json();
        const normalizedCandles = Array.isArray(candlesData.candles) ? candlesData.candles : [];
        pendingCandlesRef.current = normalizedCandles;

        if (candleSeriesRef.current) {
          candleSeriesRef.current.setData(normalizedCandles);
          chartRef.current?.timeScale().fitContent();
        }

        // Get trading status
        const statusRes = await fetch(`${getAPIBase()}/api/charts/trading-status`);
        if (statusRes.ok) {
          const statusData = await statusRes.json();
          setIsTrading(statusData.is_trading);
        }

        setLastUpdate(new Date());
        setLoading(false);
      } catch (err) {
        setError(err.message);
        setLoading(false);
      }
    };

    fetchChartData();
  }, [symbol, timeframe]);

  // WebSocket connection for real-time updates
  useEffect(() => {
    if (!symbol) return;

    const wsUrl = `${getWebSocketBase()}/ws/charts/${symbol}`;
    let pingInterval = null;
    let isUnmounting = false;

    try {
      const ws = new WebSocket(wsUrl);

      ws.onopen = () => {
        console.log(`WebSocket connected for ${symbol}`);
        setWsWarning(null);

        // Send keep-alive ping every 30 seconds
        pingInterval = setInterval(() => {
          if (ws.readyState === WebSocket.OPEN) {
            ws.send('ping');
          }
        }, 30000);
      };

      ws.onmessage = (event) => {
        try {
          const rawPayload = String(event.data ?? '').trim();
          if (!rawPayload) {
            return;
          }

          const normalizedPayload = rawPayload.toLowerCase();
          if (
            normalizedPayload === 'pong' ||
            normalizedPayload === '"pong"' ||
            normalizedPayload.includes('"type":"pong"') ||
            normalizedPayload.includes('"event":"pong"')
          ) {
            return;
          }

          if (!(rawPayload.startsWith('{') || rawPayload.startsWith('['))) {
            return;
          }

          const data = JSON.parse(rawPayload);
          if (data?.type === 'pong' || data?.event === 'pong') {
            return;
          }

          if (data.type === 'candle_update') {
            // Update with new candle
            if (candleSeriesRef.current) {
              candleSeriesRef.current.update(data.candle);
            } else {
              latestCandleRef.current = data.candle;
            }
            setLastUpdate(new Date());
          } else {
            // Initial data
            const normalizedCandles = Array.isArray(data.candles) ? data.candles : [];
            pendingCandlesRef.current = normalizedCandles;

            if (candleSeriesRef.current) {
              candleSeriesRef.current.setData(normalizedCandles);
              chartRef.current?.timeScale().fitContent();
            }
          }
        } catch (err) {
          // Ignore malformed keep-alive payloads and non-JSON messages.
          if (String(event.data ?? '').toLowerCase().includes('pong')) {
            return;
          }
          console.error('Error processing WebSocket message:', err);
        }
      };

      ws.onerror = (err) => {
        if (isUnmounting) {
          return;
        }
        console.error('WebSocket error:', err);
        setWsWarning('Live updates unavailable. Showing latest fetched data.');
      };

      ws.onclose = () => {
        if (isUnmounting) {
          return;
        }
        console.log(`WebSocket disconnected for ${symbol}`);
        setWsWarning('Live updates disconnected. Reconnect by refreshing the page.');
        if (pingInterval) {
          clearInterval(pingInterval);
        }
      };

      return () => {
        isUnmounting = true;
        if (pingInterval) {
          clearInterval(pingInterval);
        }
        if (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING) {
          ws.close();
        }
      };
    } catch (err) {
      setWsWarning(`Live updates unavailable: ${err.message}`);
    }
  }, [symbol]);

  const handleTimeframeChange = useCallback((newTimeframe) => {
    if (newTimeframe === timeframe) {
      return;
    }

    if (typeof onTimeframeChange === 'function') {
      onTimeframeChange(newTimeframe);
    }
  }, [onTimeframeChange, timeframe]);

  return (
    <div className="chart-container">
      <div className="chart-header">
        <div className="chart-info">
          <h2 className="chart-title">{symbol}</h2>
          {metadata && (
            <div className="chart-metadata">
              <span className="metadata-item">
                <strong>Exchange:</strong> {metadata.exchange}
              </span>
              <span className="metadata-item">
                <strong>Currency:</strong> {metadata.currency}
              </span>
              <span className="metadata-item">
                <strong>Hours:</strong> {metadata.tradingStart || metadata.trading_hours?.start || '09:00'} - {metadata.tradingEnd || metadata.trading_hours?.end || '16:00'} WIB
              </span>
              <span className={`metadata-item trading-status ${isTrading ? 'open' : 'closed'}`}>
                <strong>Status:</strong> {isTrading ? '🟢 Open' : '🔴 Closed'}
              </span>
            </div>
          )}
          {lastUpdate && (
            <p className="last-update">Last update: {formatDate(lastUpdate.getTime() / 1000)}</p>
          )}
          {wsWarning && (
            <p className="last-update" style={{ color: 'var(--accent-yellow)' }}>{wsWarning}</p>
          )}
        </div>

        <div className="chart-controls">
          <div className={`timeframe-buttons ${isMobile ? 'mobile' : ''}`}>
            {timeframes.map((tf) => (
              <button
                key={tf}
                className={`timeframe-btn ${timeframe === tf ? 'active' : ''}`}
                onClick={() => handleTimeframeChange(tf)}
                title={`${tf} timeframe`}
              >
                {tf}
              </button>
            ))}
          </div>
        </div>
      </div>

      {loading && <div className="loading">Loading chart...</div>}
      {error && <div className="error-message">⚠️ {error}</div>}

      <div
        ref={containerRef}
        className="chart-canvas"
        style={{
          display: loading || error ? 'none' : 'block',
        }}
      />
    </div>
  );
};

export default ChartComponent;
