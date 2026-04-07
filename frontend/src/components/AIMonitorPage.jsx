import React, { useCallback, useEffect, useMemo, useState } from 'react';
import toast from '../store/toastStore';
import apiService from '../utils/apiService';
import '../styles/ai-monitor.css';

const levelClassName = {
  info: 'info',
  warning: 'warning',
  error: 'error',
};

export default function AIMonitorPage({ onNavigate }) {
  const [overview, setOverview] = useState(null);
  const [logs, setLogs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [autoRefreshSeconds, setAutoRefreshSeconds] = useState(20);

  const latestTimestamp = useMemo(() => {
    if (!logs.length) return '-';
    return new Date(logs[0].timestamp).toLocaleString('id-ID', {
      timeZone: 'Asia/Jakarta',
      hour12: false,
    });
  }, [logs]);

  const loadMonitorData = useCallback(async (silent = false) => {
    if (!silent) {
      setLoading(true);
    }

    try {
      const [overviewResult, logsResult] = await Promise.allSettled([
        apiService.getAIOverview(),
        apiService.getAILogs(120),
      ]);

      if (overviewResult.status === 'fulfilled') {
        setOverview(overviewResult.value || null);
      } else if (!silent) {
        toast.error(`Failed to load AI monitor: ${overviewResult.reason?.message || 'Unknown error'}`);
      }

      if (logsResult.status === 'fulfilled') {
        setLogs(Array.isArray(logsResult.value) ? logsResult.value : []);
      } else if (!silent) {
        toast.error(`Failed to load AI logs: ${logsResult.reason?.message || 'Unknown error'}`);
      }
    } finally {
      if (!silent) {
        setLoading(false);
      }
    }
  }, []);

  useEffect(() => {
    let active = true;

    const bootstrap = async () => {
      try {
        const settings = await apiService.getUserSettings();
        if (active) {
          const requestedRefresh = Number(settings?.aiMonitorRefreshSeconds);
          if (Number.isFinite(requestedRefresh)) {
            setAutoRefreshSeconds(Math.max(5, Math.min(300, Math.round(requestedRefresh))));
          }
        }
      } catch (_) {
        // Keep default refresh interval when settings endpoint is unavailable.
      }

      await loadMonitorData(false);
      if (!active) return;
    };

    bootstrap();

    return () => {
      active = false;
    };
  }, [loadMonitorData]);

  useEffect(() => {
    const timer = setInterval(() => {
      loadMonitorData(true);
    }, autoRefreshSeconds * 1000);

    return () => {
      clearInterval(timer);
    };
  }, [autoRefreshSeconds, loadMonitorData]);

  const handleRefresh = async () => {
    setRefreshing(true);
    await loadMonitorData(true);
    setRefreshing(false);
    toast.success('AI monitor refreshed.');
  };

  const handleCreateCheckpoint = async () => {
    try {
      await apiService.createAILog({
        level: 'info',
        eventType: 'manual_checkpoint',
        message: 'Manual AI checkpoint captured from monitor dashboard.',
        payload: {
          source: 'frontend',
        },
      });
      await loadMonitorData(true);
      toast.success('Checkpoint log created.');
    } catch (error) {
      toast.error(`Failed to create checkpoint: ${error.message}`);
    }
  };

  if (loading) {
    return (
      <div className="ai-monitor-page">
        <h1>🧠 AI Monitor</h1>
        <div className="ai-card">
          <h2>Loading AI telemetry...</h2>
          <p>Please wait while we gather model and learning pipeline status.</p>
        </div>
      </div>
    );
  }

  const metrics = overview?.metrics || {};
  const model = overview?.model || {};
  const pipeline = Array.isArray(overview?.learningPipeline) ? overview.learningPipeline : [];
  const isFallbackTelemetry = overview?.source === 'fallback';

  return (
    <div className="ai-monitor-page">
      <div className="ai-header">
        <div>
          <h1>🧠 AI Monitor</h1>
          <p>
            Observe AI scoring pipeline, machine learning lifecycle, and event logs in real time.
            {` Auto refresh: ${autoRefreshSeconds}s.`}
          </p>
        </div>
        <div className="ai-header-actions">
          <button type="button" className="btn-secondary" onClick={() => onNavigate?.('settings')}>
            AI Settings
          </button>
          <button type="button" className="btn-secondary" onClick={handleCreateCheckpoint}>
            Add Checkpoint Log
          </button>
          <button type="button" className="btn-primary" onClick={handleRefresh} disabled={refreshing}>
            {refreshing ? 'Refreshing...' : 'Refresh Data'}
          </button>
        </div>
      </div>

      <section className="ai-metrics-grid">
        <article className="ai-metric-card">
          <h3>Model Artifact</h3>
          <strong>{model.artifact || 'Not trained yet'}</strong>
          <span>Last train: {model.lastTrainedAt ? new Date(model.lastTrainedAt).toLocaleString('id-ID', { timeZone: 'Asia/Jakarta' }) : '-'}</span>
        </article>

        <article className="ai-metric-card">
          <h3>Dataset Rows</h3>
          <strong>{Number(model.datasetRows || 0).toLocaleString('id-ID')}</strong>
          <span>Universe size: {Array.isArray(model.preferredUniverse) ? model.preferredUniverse.length : 0}</span>
        </article>

        <article className="ai-metric-card">
          <h3>Trading Signals</h3>
          <strong>{Number(metrics.processedEvents || 0).toLocaleString('id-ID')}</strong>
          <span>Active trades: {metrics.activeTrades ?? 0}</span>
        </article>

        <article className="ai-metric-card">
          <h3>Risk Watch</h3>
          <strong>{Number(metrics.warningEvents || 0)}</strong>
          <span>Error events: {Number(metrics.errorEvents || 0)}</span>
        </article>
      </section>

      {isFallbackTelemetry && (
        <section className="ai-card">
          <div className="ai-card-header">
            <h2>Fallback Mode Active</h2>
            <span>Backend AI endpoint unavailable</span>
          </div>
          <p>
            AI monitor endpoint is currently returning 404. Dashboard is running with
            fallback telemetry from bot status until backend AI routes are active.
          </p>
        </section>
      )}

      <section className="ai-card">
        <div className="ai-card-header">
          <h2>Learning Pipeline</h2>
          <span className="ai-timestamp">Last log: {latestTimestamp}</span>
        </div>
        <div className="ai-pipeline-list">
          {pipeline.map((item) => (
            <div className="ai-pipeline-item" key={item.stage}>
              <div>
                <strong>{item.stage}</strong>
                <p>{item.detail}</p>
              </div>
              <span className={`pipeline-status ${String(item.status || 'running').toLowerCase()}`}>
                {item.status}
              </span>
            </div>
          ))}
          {!pipeline.length && <p>No pipeline stages reported.</p>}
        </div>
      </section>

      <section className="ai-card">
        <div className="ai-card-header">
          <h2>AI Activity Logs</h2>
          <span>{logs.length} entries</span>
        </div>

        <div className="ai-log-list">
          {logs.map((log) => (
            <article className="ai-log-item" key={log.id || `${log.timestamp}-${log.eventType}`}>
              <div className="ai-log-meta">
                <span className={`log-level ${levelClassName[log.level] || 'info'}`}>{log.level}</span>
                <span className="log-event">{log.eventType}</span>
                <span className="log-time">
                  {new Date(log.timestamp).toLocaleString('id-ID', {
                    timeZone: 'Asia/Jakarta',
                    hour12: false,
                  })}
                </span>
              </div>
              <p className="log-message">{log.message}</p>
              {log.payload && Object.keys(log.payload).length > 0 && (
                <pre className="log-payload">{JSON.stringify(log.payload, null, 2)}</pre>
              )}
            </article>
          ))}
          {!logs.length && <p>No AI log entries available.</p>}
        </div>
      </section>
    </div>
  );
}
