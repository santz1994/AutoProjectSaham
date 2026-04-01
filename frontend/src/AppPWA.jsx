/**
 * App Integration Wrapper
 * 
 * Sets up:
 * - Service Worker registration
 * - Manifest loading
 * - PWA install button
 * - Responsive design hook
 * - Global styles with safe area support
 */

import React, { useEffect } from 'react';
import PWAInstallButton from './components/PWAInstallButton';
import useResponsive from './hooks/useResponsive';
import './App.css';

/**
 * App Component
 * Root component with PWA and responsive setup
 */
function App() {
  const { cssVariables, darkMode, colorScheme } = useResponsive();

  /**
   * Register Service Worker on mount
   */
  useEffect(() => {
    const registerServiceWorker = async () => {
      if (typeof window === 'undefined' || !('serviceWorker' in navigator)) {
        console.log('[App] Service Worker not supported');
        return;
      }

      try {
        console.log('[App] Registering Service Worker...');
        const registration = await navigator.serviceWorker.register(
          '/src/service-worker.js',
          { scope: '/' }
        );

        console.log('[App] Service Worker registered:', registration);

        // Register for push notifications
        if ('PushManager' in window && Notification.permission === 'granted') {
          try {
            const subscription = await registration.pushManager.subscribe({
              userVisibleOnly: true,
              applicationServerKey: process.env.VITE_VAPID_PUBLIC_KEY
            });
            console.log('[App] Push notification subscription created');
          } catch (error) {
            console.warn('[App] Push notification subscription failed:', error);
          }
        }
      } catch (error) {
        console.error('[App] Service Worker registration failed:', error);
      }
    };

    registerServiceWorker();
  }, []);

  /**
   * Load manifest
   */
  useEffect(() => {
    if (typeof document === 'undefined') return;

    const existingLink = document.querySelector('link[rel="manifest"]');
    if (!existingLink) {
      const link = document.createElement('link');
      link.rel = 'manifest';
      link.href = '/manifest.json';
      document.head.appendChild(link);
      console.log('[App] Manifest loaded');
    }
  }, []);

  /**
   * Apply theme and safe area CSS variables
   */
  useEffect(() => {
    if (typeof document === 'undefined') return;

    const root = document.documentElement;

    // Apply safe area and viewport CSS variables
    Object.entries(cssVariables).forEach(([key, value]) => {
      root.style.setProperty(key, value);
    });

    // Apply theme class
    if (darkMode) {
      root.classList.add('dark-theme');
      root.classList.remove('light-theme');
    } else {
      root.classList.add('light-theme');
      root.classList.remove('dark-theme');
    }
  }, [cssVariables, darkMode]);

  /**
   * Apply theme to meta tag for address bar
   */
  useEffect(() => {
    if (typeof document === 'undefined') return;

    let metaThemeColor = document.querySelector('meta[name="theme-color"]');
    if (!metaThemeColor) {
      metaThemeColor = document.createElement('meta');
      metaThemeColor.name = 'theme-color';
      document.head.appendChild(metaThemeColor);
    }

    metaThemeColor.content = darkMode ? '#131722' : '#ffffff';
  }, [darkMode]);

  return (
    <div className="app-root" style={cssVariables} data-theme={colorScheme}>
      {/* PWA Install Button */}
      <PWAInstallButton variant="floating" position="bottom-right" />

      {/* Main Content */}
      <main className="app-main">
        <header className="app-header">
          <h1>AutoSaham</h1>
          <p>Autonomous Trading Toolkit for IDX</p>
        </header>

        <section className="app-content">
          {/* Dashboard/Charts would go here */}
          <div className="content-placeholder">
            <p>Content coming soon...</p>
            <p>Import your components here</p>
          </div>
        </section>
      </main>

      {/* Footer */}
      <footer className="app-footer">
        <p>AutoSaham © 2026 | Jakarta Timezone (WIB: UTC+7)</p>
      </footer>
    </div>
  );
}

export default App;
