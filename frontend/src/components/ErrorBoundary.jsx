/**
 * Error Boundary Component
 * Catches JavaScript errors anywhere in the component tree
 * and displays a fallback UI instead of crashing the entire app
 */

import React, { Component } from 'react';
import './ErrorBoundary.css';

class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = {
      hasError: false,
      error: null,
      errorInfo: null,
      errorCount: 0,
    };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true };
  }

  componentDidCatch(error, errorInfo) {
    // Log error details
    console.error('Error Boundary caught an error:', error, errorInfo);

    this.setState((prevState) => ({
      error,
      errorInfo,
      errorCount: prevState.errorCount + 1,
    }));

    // You can also log to an error reporting service here
    // logErrorToService(error, errorInfo);
  }

  handleReset = () => {
    this.setState({
      hasError: false,
      error: null,
      errorInfo: null,
    });

    // Call optional onReset callback
    if (this.props.onReset) {
      this.props.onReset();
    }
  };

  handleReload = () => {
    window.location.reload();
  };

  render() {
    if (this.state.hasError) {
      // Custom fallback UI
      if (this.props.fallback) {
        return this.props.fallback({
          error: this.state.error,
          errorInfo: this.state.errorInfo,
          onReset: this.handleReset,
        });
      }

      // Default fallback UI
      return (
        <div className="error-boundary" role="alert">
          <div className="error-boundary-content">
            <div className="error-icon" aria-hidden="true">
              ⚠️
            </div>

            <h1 className="error-title">Oops! Something went wrong</h1>

            <p className="error-message">
              We encountered an unexpected error. Don't worry, your data is safe.
            </p>

            {this.state.errorCount > 2 && (
              <div className="error-warning">
                <p>
                  This error has occurred {this.state.errorCount} times. There might be a persistent
                  issue. Try reloading the page.
                </p>
              </div>
            )}

            <div className="error-actions">
              <button className="error-button primary" onClick={this.handleReset}>
                Try Again
              </button>
              <button className="error-button secondary" onClick={this.handleReload}>
                Reload Page
              </button>
            </div>

            {process.env.NODE_ENV === 'development' && this.state.error && (
              <details className="error-details">
                <summary className="error-details-summary">Error Details (Dev Only)</summary>
                <div className="error-stack">
                  <h3>Error:</h3>
                  <pre>{this.state.error.toString()}</pre>

                  <h3>Component Stack:</h3>
                  <pre>{this.state.errorInfo?.componentStack}</pre>
                </div>
              </details>
            )}
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}

// Functional wrapper for hooks compatibility
export const withErrorBoundary = (Component, errorBoundaryProps = {}) => {
  return (props) => (
    <ErrorBoundary {...errorBoundaryProps}>
      <Component {...props} />
    </ErrorBoundary>
  );
};

export default ErrorBoundary;
