/**
 * Stats Card Component
 * Reusable statistics display card
 */
import React from 'react';
import './StatsCard.css';

export default function StatsCard({ 
  title, 
  value, 
  change, 
  icon, 
  trend = 'neutral',
  subtitle,
  loading = false 
}) {
  if (loading) {
    return (
      <div className="stats-card loading">
        <div className="stats-card-skeleton" />
      </div>
    );
  }

  const trendIcon = trend === 'up' ? '📈' : trend === 'down' ? '📉' : '➖';
  const trendClass = trend === 'up' ? 'positive' : trend === 'down' ? 'negative' : 'neutral';

  return (
    <div className={`stats-card ${trendClass}`}>
      <div className="stats-card-header">
        <span className="stats-card-icon">{icon}</span>
        <span className="stats-card-title">{title}</span>
      </div>
      
      <div className="stats-card-value">{value}</div>
      
      {subtitle && (
        <div className="stats-card-subtitle">{subtitle}</div>
      )}
      
      {change !== undefined && (
        <div className={`stats-card-change ${trendClass}`}>
          <span className="trend-icon">{trendIcon}</span>
          <span>{change}</span>
        </div>
      )}
    </div>
  );
}
