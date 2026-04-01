/**
 * Explainability Dashboard Component
 * ===================================
 * 
 * Shows model explainability:
 * - Feature importance ranking
 * - SHAP value contributions
 * - Prediction confidence
 * - Feature analysis
 * 
 * Author: AutoSaham Team
 * Version: 1.0.0
 */

import React, { useState, useEffect, useCallback } from 'react';
import useResponsive from '../hooks/useResponsive';
import './ExplainabilityDashboard.css';

const ExplainabilityDashboard = ({ symbol = 'BBCA.JK', theme = 'dark' }) => {
  const { isMobile, isTablet } = useResponsive();
  const [featureImportance, setFeatureImportance] = useState([]);
  const [explanation, setExplanation] = useState(null);
  const [selectedFeature, setSelectedFeature] = useState(null);
  const [featureAnalysis, setFeatureAnalysis] = useState(null);
  const [metrics, setMetrics] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [inputFeatures, setInputFeatures] = useState({});
  const [supportedFeatures, setSupportedFeatures] = useState([]);

  // Color scheme
  const colors = {
    dark: {
      background: '#131722',
      textColor: '#d1d5db',
      panelBg: '#1e222d',
      positiveColor: '#26a69a',
      negativeColor: '#f23645',
      neutralColor: '#6a8caf',
    },
    light: {
      background: '#ffffff',
      textColor: '#1f2937',
      panelBg: '#f9fafb',
      positiveColor: '#10b981',
      negativeColor: '#ef4444',
      neutralColor: '#3b82f6',
    },
  };

  const themeColors = colors[theme] || colors.dark;

  // Fetch feature importance
  useEffect(() => {
    const fetchFeatureImportance = async () => {
      try {
        setLoading(true);
        const response = await fetch(`/api/explainability/features?limit=15`);
        
        if (!response.ok) {
          throw new Error(`Failed to fetch features: ${response.statusText}`);
        }
        
        const data = await response.json();
        setFeatureImportance(data);
      } catch (err) {
        setError(err.message);
        console.error('Feature importance fetch error:', err);
      } finally {
        setLoading(false);
      }
    };

    fetchFeatureImportance();
  }, []);

  // Fetch model metrics
  useEffect(() => {
    const fetchMetrics = async () => {
      try {
        const response = await fetch('/api/explainability/metrics');
        
        if (response.ok) {
          const data = await response.json();
          setMetrics(data);
        }
      } catch (err) {
        console.warn('Could not fetch metrics:', err);
      }
    };

    fetchMetrics();
  }, []);

  // Fetch supported features
  useEffect(() => {
    const fetchSupportedFeatures = async () => {
      try {
        const response = await fetch('/api/explainability/supported-features');
        
        if (response.ok) {
          const data = await response.json();
          setSupportedFeatures(data.features);
        }
      } catch (err) {
        console.warn('Could not fetch supported features:', err);
      }
    };

    fetchSupportedFeatures();
  }, []);

  // Analyze feature
  const handleAnalyzeFeature = useCallback(
    async (featureName) => {
      try {
        const response = await fetch(`/api/explainability/feature/${featureName}`);
        
        if (!response.ok) {
          throw new Error('Failed to analyze feature');
        }
        
        const data = await response.json();
        setFeatureAnalysis(data);
        setSelectedFeature(featureName);
      } catch (err) {
        setError(err.message);
      }
    },
    []
  );

  // Explain prediction
  const handleExplainPrediction = useCallback(async () => {
    try {
      if (Object.keys(inputFeatures).length === 0) {
        setError('Please enter feature values');
        return;
      }

      const response = await fetch('/api/explainability/explain', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          features: inputFeatures,
          top_features: 10,
        }),
      });

      if (!response.ok) {
        throw new Error('Failed to explain prediction');
      }

      const data = await response.json();
      setExplanation(data);
      setError(null);
    } catch (err) {
      setError(err.message);
    }
  }, [inputFeatures]);

  // Handle feature input change
  const handleFeatureInput = (featureName, value) => {
    try {
      const numValue = parseFloat(value);
      setInputFeatures({
        ...inputFeatures,
        [featureName]: numValue,
      });
    } catch (err) {
      console.error('Invalid number:', err);
    }
  };

  const getPredictionColor = (predictionClass) => {
    switch (predictionClass) {
      case 'BUY':
        return themeColors.positiveColor;
      case 'SELL':
        return themeColors.negativeColor;
      case 'HOLD':
        return themeColors.neutralColor;
      default:
        return themeColors.textColor;
    }
  };

  const getContributionColor = (shapeValue) => {
    if (shapeValue > 0) return themeColors.positiveColor;
    if (shapeValue < 0) return themeColors.negativeColor;
    return themeColors.neutralColor;
  };

  return (
    <div
      className="explainability-dashboard"
      style={{ backgroundColor: themeColors.background, color: themeColors.textColor }}
    >
      <div className="dashboard-header">
        <h1>🧠 Model Explainability Dashboard</h1>
        <p className="subtitle">Understand your model's predictions with SHAP</p>
      </div>

      {error && <div className="error-message">⚠️ {error}</div>}

      {loading && <div className="loading">Loading explainability data...</div>}

      {!loading && (
        <div className="dashboard-grid">
          {/* Feature Importance Panel */}
          <div
            className="dashboard-panel feature-importance-panel"
            style={{ backgroundColor: themeColors.panelBg }}
          >
            <h2>📊 Feature Importance</h2>
            <div className="feature-importance-list">
              {featureImportance.map((feature, idx) => (
                <div
                  key={idx}
                  className="feature-importance-item"
                  onClick={() => handleAnalyzeFeature(feature.feature_name)}
                  style={{ cursor: 'pointer' }}
                >
                  <div className="feature-rank">{feature.rank}</div>
                  <div className="feature-details">
                    <div className="feature-name">{feature.feature_name}</div>
                    <div className="feature-bar-container">
                      <div
                        className="feature-bar"
                        style={{
                          width: `${feature.importance_percent}%`,
                          backgroundColor: themeColors.positiveColor,
                        }}
                      />
                    </div>
                  </div>
                  <div className="feature-percent">{feature.importance_percent.toFixed(1)}%</div>
                </div>
              ))}
            </div>
          </div>

          {/* Model Metrics Panel */}
          {metrics && (
            <div
              className="dashboard-panel metrics-panel"
              style={{ backgroundColor: themeColors.panelBg }}
            >
              <h2>📈 Model Metrics</h2>
              <div className="metrics-grid">
                <div className="metric-card">
                  <div className="metric-label">Accuracy</div>
                  <div className="metric-value">{(metrics.accuracy * 100).toFixed(1)}%</div>
                </div>
                <div className="metric-card">
                  <div className="metric-label">Precision</div>
                  <div className="metric-value">{(metrics.precision * 100).toFixed(1)}%</div>
                </div>
                <div className="metric-card">
                  <div className="metric-label">Recall</div>
                  <div className="metric-value">{(metrics.recall * 100).toFixed(1)}%</div>
                </div>
                <div className="metric-card">
                  <div className="metric-label">F1 Score</div>
                  <div className="metric-value">{(metrics.f1_score * 100).toFixed(1)}%</div>
                </div>
                <div className="metric-card">
                  <div className="metric-label">AUC-ROC</div>
                  <div className="metric-value">{(metrics.auc_roc * 100).toFixed(1)}%</div>
                </div>
              </div>
            </div>
          )}

          {/* Prediction Explanation Panel */}
          <div
            className="dashboard-panel explanation-panel"
            style={{ backgroundColor: themeColors.panelBg }}
          >
            <h2>🎯 Explain a Prediction</h2>

            <div className="feature-inputs">
              {supportedFeatures.slice(0, 5).map((feature) => (
                <div key={feature} className="feature-input-group">
                  <label>{feature}</label>
                  <input
                    type="number"
                    placeholder="0.0"
                    onChange={(e) => handleFeatureInput(feature, e.target.value)}
                    style={{
                      backgroundColor: themeColors.panelBg,
                      color: themeColors.textColor,
                      borderColor: themeColors.neutralColor,
                    }}
                  />
                </div>
              ))}
            </div>

            <button
              className="explain-button"
              onClick={handleExplainPrediction}
              style={{
                backgroundColor: themeColors.neutralColor,
                color: '#fff',
              }}
            >
              Explain Prediction
            </button>

            {explanation && (
              <div className="prediction-result">
                <div
                  className="prediction-badge"
                  style={{ backgroundColor: getPredictionColor(explanation.prediction_class) }}
                >
                  {explanation.prediction_class}
                </div>
                <div className="prediction-stats">
                  <div>Prediction: {(explanation.prediction * 100).toFixed(1)}%</div>
                  <div>Confidence: {(explanation.confidence * 100).toFixed(1)}%</div>
                </div>

                <h3>Top Contributing Features (SHAP)</h3>
                <div className="shap-contributions">
                  {explanation.feature_contributions.slice(0, 5).map((contrib, idx) => (
                    <div key={idx} className="shap-item">
                      <div className="shap-feature">{contrib.feature}</div>
                      <div
                        className="shap-bar"
                        style={{
                          width: `${Math.abs(contrib.shap_value) * 500}px`,
                          backgroundColor: getContributionColor(contrib.shap_value),
                          marginLeft:
                            contrib.shap_value < 0 ? `${Math.abs(contrib.shap_value) * 500}px` : 0,
                        }}
                      >
                        <span>{contrib.shap_value.toFixed(3)}</span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* Feature Analysis Panel */}
          {featureAnalysis && (
            <div
              className="dashboard-panel analysis-panel"
              style={{ backgroundColor: themeColors.panelBg }}
            >
              <h2>🔍 Feature Analysis: {selectedFeature}</h2>
              <div className="analysis-stats">
                <div className="stat-row">
                  <span>Correlation:</span>
                  <strong>{featureAnalysis.correlation_with_prediction.toFixed(3)}</strong>
                </div>
                <div className="stat-row">
                  <span>Min:</span>
                  <strong>{featureAnalysis.min_value.toFixed(2)}</strong>
                </div>
                <div className="stat-row">
                  <span>Max:</span>
                  <strong>{featureAnalysis.max_value.toFixed(2)}</strong>
                </div>
                <div className="stat-row">
                  <span>Mean:</span>
                  <strong>{featureAnalysis.mean_value.toFixed(2)}</strong>
                </div>
                <div className="stat-row">
                  <span>Std Dev:</span>
                  <strong>{featureAnalysis.std_value.toFixed(2)}</strong>
                </div>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default ExplainabilityDashboard;
