import React, { useCallback, useEffect, useMemo, useState } from 'react';
import Button from './Button';
import ChartComponent from './ChartComponent';
import apiService from '../utils/apiService';
import toast from '../store/toastStore';
import '../styles/ai-graph.css';

const FALLBACK_SYMBOLS_BY_MARKET = {
  stocks: [
    'BBCA.JK', 'BMRI.JK', 'BBRI.JK', 'BBNI.JK', 'BBTN.JK',
    'TLKM.JK', 'ASII.JK', 'UNVR.JK', 'INDF.JK', 'ICBP.JK',
    'KLBF.JK', 'ADRO.JK', 'ANTM.JK', 'PGAS.JK', 'SMGR.JK',
    'CPIN.JK', 'EXCL.JK', 'MDKA.JK', 'MEDC.JK', 'UNTR.JK',
  ],
  forex: [
    'EURUSD=X', 'GBPUSD=X', 'USDJPY=X', 'AUDUSD=X',
    'USDCHF=X', 'USDCAD=X', 'NZDUSD=X', 'EURJPY=X', 'USDIDR=X',
  ],
  crypto: [
    'BTC-USD', 'ETH-USD', 'SOL-USD', 'BNB-USD', 'XRP-USD', 'ADA-USD', 'DOGE-USD',
  ],
  index: [
    '^GSPC', '^IXIC', '^DJI', '^HSI', '^N225',
  ],
};

const DEFAULT_SYMBOLS = FALLBACK_SYMBOLS_BY_MARKET.stocks;

function getFallbackSymbols(market = 'stocks') {
  const normalizedMarket = String(market || 'stocks').toLowerCase();
  if (normalizedMarket === 'all') {
    return [...new Set([
      ...FALLBACK_SYMBOLS_BY_MARKET.stocks,
      ...FALLBACK_SYMBOLS_BY_MARKET.forex,
      ...FALLBACK_SYMBOLS_BY_MARKET.crypto,
      ...FALLBACK_SYMBOLS_BY_MARKET.index,
    ])];
  }
  return FALLBACK_SYMBOLS_BY_MARKET[normalizedMarket] || DEFAULT_SYMBOLS;
}
const MARKET_OPTIONS = [
  { value: 'stocks', label: 'Saham (IDX)' },
  { value: 'forex', label: 'Forex' },
  { value: 'crypto', label: 'Blockchain/Crypto' },
  { value: 'index', label: 'Global Index' },
  { value: 'all', label: 'All Markets' },
];
const TIMEFRAME_OPTIONS = ['1m', '5m', '15m', '30m', '1h', '4h', '1d', '1w', '1mo'];
const HORIZON_OPTIONS = [8, 12, 16, 24, 32];

const SIGNAL_CLASS = {
  STRONG_BUY: 'bullish',
  BUY: 'bullish',
  HOLD: 'neutral',
  SELL: 'bearish',
  STRONG_SELL: 'bearish',
};

function inferCurrencyProfile(symbol = '', market = 'stocks') {
  const upper = String(symbol || '').toUpperCase();

  if (upper.endsWith('.JK') || market === 'stocks') {
    return { currency: 'IDR', digits: 0 };
  }

  if (upper.endsWith('=X') || market === 'forex') {
    const pair = upper.replace('=X', '').replace('/', '');
    if (pair.length === 6) {
      const quote = pair.slice(3);
      if (quote === 'JPY') return { currency: 'JPY', digits: 3 };
      if (quote === 'IDR') return { currency: 'IDR', digits: 0 };
      return { currency: quote, digits: 5 };
    }
    return { currency: 'USD', digits: 5 };
  }

  if (upper.includes('-')) {
    const quote = upper.split('-').pop();
    if (quote === 'IDR') return { currency: 'IDR', digits: 0 };
    if (/^[A-Z]{3}$/.test(quote || '')) {
      return { currency: quote, digits: 2 };
    }
  }

  return { currency: 'USD', digits: 2 };
}

function formatPrice(value, currency = 'IDR', digits = 2) {
  const safe = Number(value);
  if (!Number.isFinite(safe)) {
    return '-';
  }
  return new Intl.NumberFormat('id-ID', {
    style: 'currency',
    currency,
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(safe);
}

function formatPercent(value) {
  const safe = Number(value);
  if (!Number.isFinite(safe)) {
    return '-';
  }
  return `${safe > 0 ? '+' : ''}${safe.toFixed(2)}%`;
}

export default function AIGraphPage({ theme = 'dark' }) {
  const [selectedMarket, setSelectedMarket] = useState('stocks');
  const [symbolOptions, setSymbolOptions] = useState(() => getFallbackSymbols('stocks'));
  const [selectedSymbol, setSelectedSymbol] = useState(() => getFallbackSymbols('stocks')[0] || 'BBCA.JK');
  const [selectedTimeframe, setSelectedTimeframe] = useState('1d');
  const [projectionHorizon, setProjectionHorizon] = useState(16);

  const [projectionMeta, setProjectionMeta] = useState(null);
  const [projectionData, setProjectionData] = useState([]);
  const [loadingProjection, setLoadingProjection] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState(null);

  const signalClassName = useMemo(() => {
    const signal = String(projectionMeta?.signal || 'HOLD').toUpperCase();
    return SIGNAL_CLASS[signal] || 'neutral';
  }, [projectionMeta]);

  useEffect(() => {
    let active = true;

    const loadUniverse = async () => {
      try {
        const payload = await apiService.getMarketUniverse(180, selectedMarket);
        const symbols = Array.isArray(payload?.symbols)
          ? payload.symbols.filter((item) => typeof item === 'string' && item.trim())
          : [];

        if (!active) {
          return;
        }

        if (symbols.length > 0) {
          setSymbolOptions(symbols);
          setSelectedSymbol((current) => (symbols.includes(current) ? current : symbols[0]));
          return;
        }

        const fallback = getFallbackSymbols(selectedMarket);
        setSymbolOptions(fallback);
        setSelectedSymbol((current) => (fallback.includes(current) ? current : fallback[0]));
      } catch (error) {
        if (active) {
          const fallback = getFallbackSymbols(selectedMarket);
          setSymbolOptions(fallback);
          setSelectedSymbol((current) => (fallback.includes(current) ? current : fallback[0]));
        }
      }
    };

    loadUniverse();
    return () => {
      active = false;
    };
  }, [selectedMarket]);

  const mapProjectionSeries = useCallback((payload) => {
    const baseTime = Number(payload?.baseTime);
    const currentPrice = Number(payload?.currentPrice);

    const basePoint = Number.isFinite(baseTime) && Number.isFinite(currentPrice) && baseTime > 0 && currentPrice > 0
      ? [{ time: baseTime, value: currentPrice }]
      : [];

    const projectionPoints = Array.isArray(payload?.projection)
      ? payload.projection
          .filter((item) => Number.isFinite(Number(item?.time)) && Number.isFinite(Number(item?.value)))
          .map((item) => ({
            time: Number(item.time),
            value: Number(item.value),
          }))
      : [];

    return [...basePoint, ...projectionPoints];
  }, []);

  const loadProjection = useCallback(
    async ({ silent = false } = {}) => {
      if (!silent) {
        setLoadingProjection(true);
      }

      try {
        const payload = await apiService.getAIProjection(
          selectedSymbol,
          selectedTimeframe,
          projectionHorizon,
          selectedMarket,
        );

        setProjectionMeta(payload);
        setProjectionData(mapProjectionSeries(payload));
        setError(null);
      } catch (err) {
        const message = err?.message || 'Failed to load AI projection';
        if (!silent) {
          toast.error(message);
        }
        setProjectionData([]);
        setError(message);
      } finally {
        if (!silent) {
          setLoadingProjection(false);
        }
      }
    },
    [mapProjectionSeries, projectionHorizon, selectedMarket, selectedSymbol, selectedTimeframe]
  );

  useEffect(() => {
    loadProjection({ silent: false });

    const timer = setInterval(() => {
      loadProjection({ silent: true });
    }, 25000);

    return () => {
      clearInterval(timer);
    };
  }, [loadProjection]);

  const handleManualRefresh = async () => {
    setRefreshing(true);
    await loadProjection({ silent: true });
    setRefreshing(false);
    toast.success('AI projection refreshed.');
  };

  const predictedMove = Number(projectionMeta?.expectedReturn || 0) * 100;
  const confidenceLabel = String(projectionMeta?.confidenceLabel || 'medium').replace('_', ' ');
  const modelConfidencePercent = Number(projectionMeta?.modelConfidence) * 100;
  const currencyProfile = inferCurrencyProfile(selectedSymbol, selectedMarket);
  const displayCurrency = currencyProfile.currency;
  const displayDigits = currencyProfile.digits;
  const projectionPoints = Array.isArray(projectionMeta?.projection) ? projectionMeta.projection : [];
  const horizonEndTime = projectionPoints.length > 0
    ? Number(projectionPoints[projectionPoints.length - 1]?.time || 0)
    : 0;
  const rationaleItems = Array.isArray(projectionMeta?.rationale)
    ? projectionMeta.rationale.filter((item) => typeof item === 'string' && item.trim())
    : [];
  const newsContext = Array.isArray(projectionMeta?.newsContext)
    ? projectionMeta.newsContext.slice(0, 3)
    : [];

  return (
    <div className="ai-graph-page">
      <div className="ai-graph-header">
        <div>
          <h1>AI Graph</h1>
          <p>
            One compact AI page for Stocks, Forex, Crypto, and Index with live chart + projection.
          </p>
        </div>
        <Button
          variant="primary"
          onClick={handleManualRefresh}
          icon={<span>🔄</span>}
          disabled={refreshing}
        >
          {refreshing ? 'Refreshing...' : 'Refresh Projection'}
        </Button>
      </div>

      <section className="ai-graph-card ai-graph-controls">
        <div className="ai-control-item">
          <label htmlFor="ai-graph-market">Market</label>
          <select
            id="ai-graph-market"
            value={selectedMarket}
            onChange={(e) => setSelectedMarket(e.target.value)}
          >
            {MARKET_OPTIONS.map((market) => (
              <option key={market.value} value={market.value}>
                {market.label}
              </option>
            ))}
          </select>
        </div>

        <div className="ai-control-item">
          <label htmlFor="ai-graph-symbol">Symbol</label>
          <select
            id="ai-graph-symbol"
            value={selectedSymbol}
            onChange={(e) => setSelectedSymbol(e.target.value)}
          >
            {symbolOptions.map((symbol) => (
              <option key={symbol} value={symbol}>
                {symbol}
              </option>
            ))}
          </select>
        </div>

        <div className="ai-control-item">
          <label htmlFor="ai-graph-timeframe">Timeframe</label>
          <select
            id="ai-graph-timeframe"
            value={selectedTimeframe}
            onChange={(e) => setSelectedTimeframe(e.target.value)}
          >
            {TIMEFRAME_OPTIONS.map((timeframe) => (
              <option key={timeframe} value={timeframe}>
                {timeframe}
              </option>
            ))}
          </select>
        </div>

        <div className="ai-control-item">
          <label htmlFor="ai-graph-horizon">Projection Horizon</label>
          <select
            id="ai-graph-horizon"
            value={projectionHorizon}
            onChange={(e) => setProjectionHorizon(Number(e.target.value))}
          >
            {HORIZON_OPTIONS.map((value) => (
              <option key={value} value={value}>
                {value} steps
              </option>
            ))}
          </select>
        </div>

        <div className="ai-control-item ai-control-live">
          <label>Live Mode</label>
          <span>WebSocket + AI refresh 25s</span>
        </div>
      </section>

      <section className="ai-graph-card ai-graph-chart-wrap">
        <div className="ai-graph-chart-title-row">
          <h2>Live + Projection Overlay</h2>
          <span className={`ai-signal-chip ${signalClassName}`}>
            {projectionMeta?.signal || 'HOLD'}
          </span>
        </div>

        <div className="ai-graph-legend">
          <span><i className="legend-live" />Live Candlestick</span>
          <span><i className="legend-ai" />AI Projection</span>
        </div>

        {error && <div className="ai-graph-error">⚠️ {error}</div>}

        {loadingProjection && (
          <div className="ai-graph-loading">Generating projection from latest model...</div>
        )}

        <ChartComponent
          symbol={selectedSymbol}
          timeframe={selectedTimeframe}
          onTimeframeChange={setSelectedTimeframe}
          theme={theme}
          projectionData={projectionData}
          showTimeframeControls={false}
        />
      </section>

      <section className="ai-graph-insight-grid">
        <article className="ai-graph-card insight-card">
          <h3>Projected Move</h3>
          <strong className={predictedMove >= 0 ? 'positive' : 'negative'}>
            {formatPercent(predictedMove)}
          </strong>
          <span>Expected return over {projectionMeta?.horizon || projectionHorizon} steps</span>
        </article>

        <article className="ai-graph-card insight-card">
          <h3>Confidence</h3>
          <strong>{formatPercent((Number(projectionMeta?.confidence || 0) * 100))}</strong>
          <span>
            {`Band: ${confidenceLabel.toUpperCase()} | Source: ${projectionMeta?.source || '-'}`}
          </span>
        </article>

        <article className="ai-graph-card insight-card">
          <h3>Current vs Target</h3>
          <strong>{formatPrice(projectionMeta?.currentPrice, displayCurrency, displayDigits)}</strong>
          <span>Target: {formatPrice(projectionMeta?.targetPrice, displayCurrency, displayDigits)}</span>
        </article>

        <article className="ai-graph-card insight-card">
          <h3>Model Architecture</h3>
          <strong>{projectionMeta?.architecture || 'fallback'}</strong>
          <span>
            Generated:{' '}
            {projectionMeta?.generatedAt
              ? new Date(projectionMeta.generatedAt).toLocaleString('id-ID', { timeZone: 'Asia/Jakarta' })
              : '-'}
          </span>
        </article>

        <article className="ai-graph-card insight-card">
          <h3>Raw Model Confidence</h3>
          <strong>
            {Number.isFinite(modelConfidencePercent)
              ? formatPercent(modelConfidencePercent)
              : 'N/A'}
          </strong>
          <span>Calibrated with realtime momentum + global sentiment</span>
        </article>

        <article className="ai-graph-card insight-card">
          <h3>Horizon End Time</h3>
          <strong>
            {horizonEndTime > 0
              ? new Date(horizonEndTime * 1000).toLocaleString('id-ID', { timeZone: 'Asia/Jakarta' })
              : '-'}
          </strong>
          <span>{`Projection horizon: ${projectionMeta?.horizon || projectionHorizon} step(s)`}</span>
        </article>
      </section>

      <section className="ai-graph-card ai-graph-reason">
        <h2>AI Rationale</h2>
        {rationaleItems.length > 0 ? (
          <ul>
            {rationaleItems.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        ) : (
          <p>{projectionMeta?.reason || 'No explanation available yet.'}</p>
        )}

        {newsContext.length > 0 && (
          <div className="ai-graph-news-context">
            <h3>Global News Context</h3>
            {newsContext.map((item) => (
              <article key={`${item.headline}-${item.timestamp}`} className="ai-news-item">
                <strong>{item.headline}</strong>
                <span>{`${item.source || 'global'} • ${item.sentiment || 'neutral'}`}</span>
              </article>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
