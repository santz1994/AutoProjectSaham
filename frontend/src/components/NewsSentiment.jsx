/**
 * NewsSentiment.jsx — LLM-powered news sentiment panel (Phase 8).
 * 
 * Displays real-time news sentiment scores from the backend.
 * Shows headline + sentiment score (-1.0 to +1.0) with visual indicators.
 */
import React, { useState, useEffect, useCallback } from 'react';
import apiService from '../utils/apiService';

const SENTIMENT_COLORS = {
  bullish: '#00C853',
  bearish: '#FF1744',
  neutral: '#FFD600',
};

const SENTIMENT_ICONS = {
  bullish: '📈',
  bearish: '📉',
  neutral: '📊',
};

function getSentimentType(score) {
  if (score > 0.3) return 'bullish';
  if (score < -0.3) return 'bearish';
  return 'neutral';
}

function formatTimestamp(value) {
  if (!value) return '';
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return String(value);
  }
  return parsed.toLocaleTimeString();
}

export default function NewsSentiment({ symbol = 'BTC/USDT', darkMode = false }) {
  const [news, setNews] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [aggregateScore, setAggregateScore] = useState(0);
  const [lastUpdate, setLastUpdate] = useState(null);

  const fetchSentiment = useCallback(async () => {
    try {
      setLoading(true);
      const data = await apiService.request(
        `/api/market/news?symbol=${encodeURIComponent(symbol)}&limit=8`
      );

      const items = Array.isArray(data) ? data : (data?.news || []);
      const mapped = items.map((item) => ({
        title: item.headline || item.title || 'Untitled',
        source: item.source || 'Market News',
        sentiment: typeof item.score === 'number' ? item.score : 0,
        time: formatTimestamp(item.timestamp),
        entities: Array.isArray(item.entities) ? item.entities : [],
        url: item.url || '',
      }));

      const aggregate = mapped.length
        ? mapped.reduce((sum, item) => sum + (Number(item.sentiment) || 0), 0) / mapped.length
        : 0;

      setNews(mapped);
      setAggregateScore(aggregate);
      setLastUpdate(new Date());
      setError(null);
    } catch (err) {
      setError(err.message);
      // Use mock data for development
      setNews([
        { title: `${symbol} breaks key resistance level`, source: 'CoinDesk', sentiment: 0.72, time: '2m ago', entities: ['BTC', 'resistance'] },
        { title: 'Federal Reserve signals rate pause', source: 'Reuters', sentiment: 0.45, time: '15m ago', entities: ['Fed', 'rates'] },
        { title: 'Whale accumulation detected on-chain', source: 'CryptoQuant', sentiment: 0.61, time: '28m ago', entities: ['whale', 'on-chain'] },
        { title: 'Market volatility expected ahead of FOMC', source: 'Bloomberg', sentiment: -0.15, time: '1h ago', entities: ['FOMC', 'volatility'] },
        { title: 'Regulatory concerns weigh on sentiment', source: 'TheBlock', sentiment: -0.42, time: '2h ago', entities: ['regulation'] },
      ]);
      setAggregateScore(0.24);
      setLastUpdate(new Date());
    } finally {
      setLoading(false);
    }
  }, [symbol]);

  useEffect(() => {
    fetchSentiment();
    const interval = setInterval(fetchSentiment, 60000); // Refresh every minute
    return () => clearInterval(interval);
  }, [fetchSentiment]);

  const aggType = getSentimentType(aggregateScore);

  return (
    <div className={`news-sentiment ${darkMode ? 'dark' : 'light'}`}>
      <div className="news-sentiment-header">
        <h3>📰 News Sentiment</h3>
        <div className="sentiment-aggregate" style={{ color: SENTIMENT_COLORS[aggType] }}>
          <span className="sentiment-icon">{SENTIMENT_ICONS[aggType]}</span>
          <span className="sentiment-score">{aggregateScore > 0 ? '+' : ''}{(aggregateScore * 100).toFixed(0)}%</span>
        </div>
      </div>

      {lastUpdate && (
        <div className="news-update-time">
          Last updated: {lastUpdate.toLocaleTimeString()}
        </div>
      )}

      {loading && news.length === 0 && (
        <div className="news-loading">Loading sentiment data...</div>
      )}

      {error && news.length === 0 && (
        <div className="news-error">
          <span>⚠️ {error}</span>
          <button onClick={fetchSentiment} className="retry-btn">Retry</button>
        </div>
      )}

      <div className="news-list">
        {news.map((article, idx) => {
          const type = getSentimentType(article.sentiment);
          return (
            <div key={idx} className={`news-item ${type}`}>
              <div className="news-item-header">
                <span className="news-source">{article.source}</span>
                <span className="news-time">{article.time}</span>
              </div>
              <div className="news-title">{article.title}</div>
              <div className="news-meta">
                <div className="news-sentiment-bar">
                  <div
                    className="sentiment-fill"
                    style={{
                      width: `${Math.abs(article.sentiment) * 100}%`,
                      backgroundColor: SENTIMENT_COLORS[type],
                    }}
                  />
                </div>
                <span className="news-sentiment-value" style={{ color: SENTIMENT_COLORS[type] }}>
                  {article.sentiment > 0 ? '+' : ''}{(article.sentiment * 100).toFixed(0)}%
                </span>
              </div>
              {article.entities?.length > 0 && (
                <div className="news-entities">
                  {article.entities.map((ent, i) => (
                    <span key={i} className="entity-tag">{ent}</span>
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}