/**
 * Component: PWAInstallButton
 * 
 * Displays install prompt for Progressive Web App
 * Features:
 * - Smart detection of installation support
 * - Shows only when installable and not already installed
 * - Animated button with download icon
 * - Error handling and fallback
 */

import React, { useState, useEffect } from 'react';
import usePWA from '../hooks/usePWA';
import './PWAInstallButton.css';

export const PWAInstallButton = ({ variant = 'floating', position = 'bottom-right' }) => {
  const {
    isInstalled,
    isOnline,
    hasUpdate,
    isUpdating,
    installPromptAvailable,
    openInstallPrompt,
    skipInstall,
    installApp,
    updateApp
  } = usePWA();

  const [showButton, setShowButton] = useState(false);
  const [showUpdatePrompt, setShowUpdatePrompt] = useState(false);

  useEffect(() => {
    // Show install button if installable and not installed
    setShowButton(installPromptAvailable && !isInstalled);
  }, [installPromptAvailable, isInstalled]);

  useEffect(() => {
    // Show update prompt if update available
    setShowUpdatePrompt(hasUpdate);
  }, [hasUpdate]);

  // Fixed floating button variant
  if (variant === 'floating') {
    return (
      <>
        {/* Install Prompt */}
        {showButton && (
          <div className={`pwa-install-fab pwa-${position}`}>
            <button
              className="pwa-install-button pwa-primary"
              onClick={openInstallPrompt}
              title="Install AutoSaham as app"
              aria-label="Install app"
            >
              <svg
                width="24"
                height="24"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                className="pwa-icon-download"
              >
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                <polyline points="7 10 12 15 17 10" />
                <line x1="12" y1="15" x2="12" y2="3" />
              </svg>
              <span className="pwa-pulse"></span>
            </button>

            {/* Tooltip */}
            <div className="pwa-tooltip">
              <p className="pwa-tooltip-title">Install AutoSaham</p>
              <p className="pwa-tooltip-text">Use offline, faster access</p>
              <button
                className="pwa-skip-button"
                onClick={skipInstall}
                type="button"
              >
                Not now
              </button>
            </div>
          </div>
        )}

        {/* Update Prompt */}
        {showUpdatePrompt && (
          <div className="pwa-update-banner">
            <div className="pwa-update-content">
              <svg
                width="20"
                height="20"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                className="pwa-icon-update"
              >
                <polyline points="23 4 23 10 17 10" />
                <path d="M20.49 15a9 9 0 1 1 .12-8.83" />
              </svg>
              <div>
                <p className="pwa-update-title">Update Available</p>
                <p className="pwa-update-text">A new version of AutoSaham is ready</p>
              </div>
            </div>

            <button
              className="pwa-update-action"
              onClick={updateApp}
              disabled={isUpdating}
              type="button"
            >
              {isUpdating ? (
                <>
                  <span className="pwa-spinner"></span>
                  Updating...
                </>
              ) : (
                'Update Now'
              )}
            </button>

            <button
              className="pwa-update-close"
              onClick={() => setShowUpdatePrompt(false)}
              type="button"
              aria-label="Dismiss update"
            >
              ✕
            </button>
          </div>
        )}

        {/* Offline Indicator */}
        {!isOnline && (
          <div className="pwa-offline-banner">
            <svg
              width="20"
              height="20"
              viewBox="0 0 24 24"
              fill="currentColor"
              className="pwa-icon-offline"
            >
              <path d="M1 9l2 2c4.97-4.97 13.03-4.97 18 0l2-2C16.93 2.93 7.08 2.93 1 9zm8 8l3 3 3-3c-1.65-1.66-4.34-1.66-6 0zm-4-4l2 2c2.76-2.76 7.24-2.76 10 0l2-2C15.14 9.14 8.87 9.14 5 13zm0 0L3 11" />
            </svg>
            <span>You are offline. Some features may be limited.</span>
          </div>
        )}
      </>
    );
  }

  // Inline banner variant
  if (variant === 'banner') {
    return (
      <>
        {showButton && (
          <div className="pwa-install-banner">
            <div className="pwa-banner-content">
              <svg
                width="24"
                height="24"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
              >
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                <polyline points="7 10 12 15 17 10" />
                <line x1="12" y1="15" x2="12" y2="3" />
              </svg>
              <div>
                <h3 className="pwa-banner-title">Add to your home screen</h3>
                <p className="pwa-banner-desc">Access AutoSaham like a native app</p>
              </div>
            </div>
            <button
              className="pwa-banner-install"
              onClick={openInstallPrompt}
              type="button"
            >
              Install
            </button>
            <button
              className="pwa-banner-close"
              onClick={skipInstall}
              type="button"
              aria-label="Dismiss"
            >
              ✕
            </button>
          </div>
        )}

        {showUpdatePrompt && (
          <div className="pwa-update-banner">
            <div className="pwa-update-content">
              <svg
                width="20"
                height="20"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
              >
                <polyline points="23 4 23 10 17 10" />
                <path d="M20.49 15a9 9 0 1 1 .12-8.83" />
              </svg>
              <div>
                <p className="pwa-update-title">Update Available</p>
                <p className="pwa-update-text">Tap to get the latest version</p>
              </div>
            </div>
            <button
              className="pwa-update-action"
              onClick={updateApp}
              disabled={isUpdating}
              type="button"
            >
              {isUpdating ? 'Updating...' : 'Update'}
            </button>
          </div>
        )}
      </>
    );
  }

  return null;
};

export default PWAInstallButton;
