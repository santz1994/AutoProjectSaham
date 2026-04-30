/**
 * Loading Skeleton Components
 * Provides loading states for better perceived performance
 */

import React from 'react';
import './LoadingSkeletons.css';

// Generic Skeleton
export const Skeleton = ({ width, height, circle, className = '' }) => (
  <div
    className={`skeleton ${circle ? 'skeleton-circle' : ''} ${className}`}
    style={{ width, height }}
    aria-label="Loading..."
    aria-busy="true"
  />
);

// Card Skeleton
export const CardSkeleton = () => (
  <div className="card-skeleton">
    <Skeleton height="1.5rem" width="60%" className="skeleton-title" />
    <div className="skeleton-content">
      <Skeleton height="1rem" width="100%" />
      <Skeleton height="1rem" width="90%" />
      <Skeleton height="1rem" width="80%" />
    </div>
  </div>
);

// Chart Skeleton
export const ChartSkeleton = () => (
  <div className="chart-skeleton">
    <div className="chart-skeleton-header">
      <Skeleton height="1.25rem" width="150px" />
      <Skeleton height="2rem" width="200px" />
    </div>
    <div className="chart-skeleton-body">
      <div className="chart-skeleton-bars">
        {Array.from({ length: 12 }).map((_, i) => (
          <Skeleton
            key={i}
            height={`${Math.random() * 60 + 40}%`}
            className="chart-skeleton-bar"
          />
        ))}
      </div>
    </div>
  </div>
);

// Table Skeleton
export const TableSkeleton = ({ rows = 5, columns = 4 }) => (
  <div className="table-skeleton">
    <div className="table-skeleton-header">
      {Array.from({ length: columns }).map((_, i) => (
        <Skeleton key={i} height="1rem" width={`${70 + Math.random() * 30}%`} />
      ))}
    </div>
    <div className="table-skeleton-body">
      {Array.from({ length: rows }).map((_, rowIndex) => (
        <div key={rowIndex} className="table-skeleton-row">
          {Array.from({ length: columns }).map((_, colIndex) => (
            <Skeleton key={colIndex} height="1rem" width={`${60 + Math.random() * 40}%`} />
          ))}
        </div>
      ))}
    </div>
  </div>
);

// Dashboard Grid Skeleton
export const DashboardSkeleton = () => (
  <div className="dashboard-skeleton">
    <div className="grid-skeleton">
      <div className="grid-item-skeleton span-full">
        <CardSkeleton />
      </div>
      <div className="grid-item-skeleton span-2">
        <CardSkeleton />
      </div>
      <div className="grid-item-skeleton">
        <CardSkeleton />
      </div>
      <div className="grid-item-skeleton span-full">
        <ChartSkeleton />
      </div>
      <div className="grid-item-skeleton span-2">
        <TableSkeleton rows={5} />
      </div>
    </div>
  </div>
);

// Spinner Component
export const Spinner = ({ size = 'md', className = '' }) => (
  <div className={`spinner spinner-${size} ${className}`} role="status" aria-label="Loading">
    <svg viewBox="0 0 50 50" className="spinner-svg">
      <circle
        className="spinner-circle"
        cx="25"
        cy="25"
        r="20"
        fill="none"
        strokeWidth="4"
      />
    </svg>
    <span className="sr-only">Loading...</span>
  </div>
);

// Progress Bar
export const ProgressBar = ({ progress = 0, label, showPercentage = true }) => (
  <div className="progress-bar-container" role="progressbar" aria-valuenow={progress} aria-valuemin="0" aria-valuemax="100">
    {label && <div className="progress-label">{label}</div>}
    <div className="progress-bar">
      <div 
        className="progress-fill" 
        style={{ width: `${Math.min(100, Math.max(0, progress))}%` }}
      />
    </div>
    {showPercentage && (
      <div className="progress-percentage">{Math.round(progress)}%</div>
    )}
  </div>
);

// Loading Overlay
export const LoadingOverlay = ({ message = 'Loading...', transparent = false }) => (
  <div className={`loading-overlay ${transparent ? 'transparent' : ''}`}>
    <div className="loading-content">
      <Spinner size="lg" />
      <p className="loading-message">{message}</p>
    </div>
  </div>
);

export default {
  Skeleton,
  CardSkeleton,
  ChartSkeleton,
  TableSkeleton,
  DashboardSkeleton,
  Spinner,
  ProgressBar,
  LoadingOverlay,
};
