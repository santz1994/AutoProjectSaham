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

import React, { useEffect, useRef, useState, useCallback } from 'react';
import { createChart, ColorType } from 'lightweight-charts';
import useResponsive from '../hooks/useResponsive';
import { getAPIBase, getWebSocketBase } from '../utils/authService';
import './ChartComponent.css';

const ChartComponent = ({ symbol = 'BBCA.JK', timeframe = '1d', onTimeframeChange, theme = 'dark' }) => {
  const containerRef = useRef(null);
  const chartRef = useRef(null);
  const candleSeriesRef = useRef(null);
  const { isMobile, isTablet, viewport } = useResponsive();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [metadata, setMetadata] = useState(null);
  const [isTrading, setIsTrading] = useState(false);
  const [lastUpdate, setLastUpdate] = useState(null);

  // Color scheme based on theme
  const colors = {
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

  const chartColors = colors[theme] || colors.dark;

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

  // Initialize chart with responsive sizing
  useEffect(() => {
    if (!containerRef.current) return;

    // Calculate responsive chart height
    const calculateChartHeight = () => {
      if (isMobile) return Math.min(viewport.height * 0.6, 400);
      if (isTablet) return Math.min(viewport.height * 0.65, 500);
      return 600;
    };

    let chart = null;
    let resizeTimer;
    let resizeObserver = null;

    // Initialize chart after container is properly sized
    const initChart = () => {
      const width = containerRef.current?.clientWidth;
      const height = calculateChartHeight();

      // Skip if container isn't sized yet
      if (!width || width < 100) {
        console.debug('Container not sized yet, waiting...', { width, height });
        return false;
      }

      try {
        // Create chart with responsive dimensions
        chart = createChart(containerRef.current, {
          layout: {
            background: { color: chartColors.background, type: ColorType.Solid },
            textColor: chartColors.textColor,
          },
          width: width,
          height: height,
          timeScale: {
            timeVisible: true,
            secondsVisible: !isMobile, // Hide seconds on mobile
            rightOffset: isMobile ? 10 : 40,
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
                minute: isMobile ? undefined : '2-digit', // Hide minutes on mobile for space
              });
            },
          },
        });

        chartRef.current = chart;

        // Add candlestick series
        const candleSeries = chart.addCandlestickSeries({
          upColor: chartColors.upColor,
          downColor: chartColors.downColor,
          borderUpColor: chartColors.borderUpColor,
          borderDownColor: chartColors.borderDownColor,
          wickUpColor: chartColors.upColor,
          wickDownColor: chartColors.downColor,
        });

        candleSeriesRef.current = candleSeries;
        return true;
      } catch (err) {
        setError(`Failed to initialize chart: ${err.message}`);
        console.error('Chart initialization error:', err);
        return false;
      }
    };

    // Use ResizeObserver to detect when container gets sized
    resizeObserver = new ResizeObserver(() => {
      if (!chartRef.current && containerRef.current?.clientWidth > 100) {
        console.debug('Container sized, initializing chart');
        initChart();
      }
    });

    if (containerRef.current) {
      resizeObserver.observe(containerRef.current);
    }

    // Try immediate initialization first
    if (!initChart()) {
      console.debug('Initial chart init failed, waiting for resize observer...');
    }

    // Enhanced resize handler with debounce
    const handleResize = () => {
      clearTimeout(resizeTimer);
      resizeTimer = setTimeout(() => {
        if (containerRef.current && chartRef.current) {
          chartRef.current.applyOptions({
            width: containerRef.current.clientWidth,
            height: calculateChartHeight(),
          });
        }
      }, 150); // Debounce to 150ms
    };

    window.addEventListener('resize', handleResize);
    return () => {
      window.removeEventListener('resize', handleResize);
      clearTimeout(resizeTimer);
      if (resizeObserver) resizeObserver.disconnect();
    };
  }, [chartColors, isMobile, isTablet, viewport.height]);

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

        if (candleSeriesRef.current && candlesData.candles) {
          candleSeriesRef.current.setData(candlesData.candles);
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

    try {
      const ws = new WebSocket(wsUrl);

      ws.onopen = () => {
        console.log(`WebSocket connected for ${symbol}`);

        // Send keep-alive ping every 30 seconds
        pingInterval = setInterval(() => {
          if (ws.readyState === WebSocket.OPEN) {
            ws.send('ping');
          }
        }, 30000);
      };

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);

          if (data.type === 'candle_update') {
            // Update with new candle
            if (candleSeriesRef.current) {
              candleSeriesRef.current.update(data.candle);
            }
            setLastUpdate(new Date());
          } else {
            // Initial data
            if (candleSeriesRef.current && data.candles) {
              candleSeriesRef.current.setData(data.candles);
              chartRef.current?.timeScale().fitContent();
            }
          }
        } catch (err) {
          console.error('Error processing WebSocket message:', err);
        }
      };

      ws.onerror = (err) => {
        console.error('WebSocket error:', err);
        setError('WebSocket connection error');
      };

      ws.onclose = () => {
        console.log(`WebSocket disconnected for ${symbol}`);
        if (pingInterval) {
          clearInterval(pingInterval);
        }
      };

      return () => {
        if (pingInterval) {
          clearInterval(pingInterval);
        }
        if (ws.readyState === WebSocket.OPEN) {
          ws.close();
        }
      };
    } catch (err) {
      setError(`Failed to connect WebSocket: ${err.message}`);
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
                <strong>Hours:</strong> {metadata.tradingStart} - {metadata.tradingEnd} WIB
              </span>
              <span className={`metadata-item trading-status ${isTrading ? 'open' : 'closed'}`}>
                <strong>Status:</strong> {isTrading ? '🟢 Open' : '🔴 Closed'}
              </span>
            </div>
          )}
          {lastUpdate && (
            <p className="last-update">Last update: {formatDate(lastUpdate.getTime() / 1000)}</p>
          )}
        </div>

        <div className="chart-controls">
          <div className={`timeframe-buttons ${isMobile ? 'mobile' : ''}`}>
            {['1m', '5m', '15m', '30m', '1h', '4h', '1d', '1w', '1mo'].map((tf) => (
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
