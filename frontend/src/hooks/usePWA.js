/**
 * Custom Hook: usePWA
 * 
 * Manages Progressive Web App functionality including:
 * - Service Worker registration and updates
 * - Installation prompt handling
 * - Online/offline status detection
 * - Cache update notifications
 * 
 * Usage:
 * ```jsx
 * const { 
 *   isInstalled,
 *   isOnline,
 *   hasUpdate,
 *   installPrompt,
 *   openInstallPrompt,
 *   skipInstall,
 *   installApp,
 *   updateApp
 * } = usePWA();
 * ```
 */

import { useState, useEffect, useCallback, useRef } from 'react';

const SERVICE_WORKER_PATH = '/service-worker.js';

const isServiceWorkerEnabledForEnvironment = () => {
  if (typeof window === 'undefined') {
    return false;
  }

  const mode = import.meta?.env?.MODE;
  const forceEnableForLocal = import.meta?.env?.VITE_ENABLE_PWA_DEV === 'true';
  const isLocalHost = ['localhost', '127.0.0.1'].includes(window.location.hostname);

  // Keep service worker enabled in test mode for hook tests.
  if (mode === 'test') {
    return true;
  }

  // In local development, default to disabled to avoid stale UI from old caches.
  if (isLocalHost && !forceEnableForLocal) {
    return false;
  }

  return true;
};

export const usePWA = () => {
  const [isInstalled, setIsInstalled] = useState(false);
  const [isOnline, setIsOnline] = useState(typeof navigator !== 'undefined' ? navigator.onLine : true);
  const [hasUpdate, setHasUpdate] = useState(false);
  const [isUpdating, setIsUpdating] = useState(false);
  const [swRegistration, setSWRegistration] = useState(null);
  const [installPrompt, setInstallPrompt] = useState(null);
  const [installPromptShown, setInstallPromptShown] = useState(false);
  const updateCheckInterval = useRef(null);

  const isStandaloneDisplayMode = useCallback(() => {
    if (typeof window === 'undefined') {
      return false;
    }
    if (typeof window.matchMedia === 'function') {
      return window.matchMedia('(display-mode: standalone)').matches;
    }
    return window.navigator.standalone === true;
  }, []);

  /**
   * Register Service Worker on mount
   */
  useEffect(() => {
    if (typeof window === 'undefined' || !('serviceWorker' in navigator)) {
      console.log('[usePWA] Service Worker not supported');
      return;
    }

    const serviceWorkerEnabled = isServiceWorkerEnabledForEnvironment();

    if (!serviceWorkerEnabled) {
      const cleanupLegacyCachesAndWorkers = async () => {
        try {
          if (typeof navigator.serviceWorker.getRegistrations === 'function') {
            const registrations = await navigator.serviceWorker.getRegistrations();
            await Promise.all(registrations.map((registration) => registration.unregister()));
          }

          if ('caches' in window && typeof caches.keys === 'function') {
            const cacheNames = await caches.keys();
            await Promise.all(
              cacheNames
                .filter((name) => name.includes('autosaham'))
                .map((name) => caches.delete(name))
            );
          }
        } catch (error) {
          console.warn('[usePWA] Cleanup skipped:', error);
        }
      };

      cleanupLegacyCachesAndWorkers();
      return;
    }

    const registerServiceWorker = async () => {
      try {
        console.log('[usePWA] Registering Service Worker...');
        const registration = await navigator.serviceWorker.register(
          SERVICE_WORKER_PATH,
          { scope: '/' }
        );

        setSWRegistration(registration);
        console.log('[usePWA] Service Worker registered:', registration);

        // Check for updates periodically (every 6 hours)
        updateCheckInterval.current = setInterval(() => {
          if (typeof registration.update === 'function') {
            registration.update();
          }
        }, 6 * 60 * 60 * 1000);

        // Listen for Service Worker updates
        if (typeof registration.addEventListener === 'function') {
          registration.addEventListener('updatefound', handleSWUpdate);
        }

        // Handle messages from Service Worker
        if (typeof navigator.serviceWorker.addEventListener === 'function') {
          navigator.serviceWorker.addEventListener('message', handleSWMessage);
        }
      } catch (error) {
        console.error('[usePWA] Service Worker registration failed:', error);
      }
    };

    registerServiceWorker();

    return () => {
      if (updateCheckInterval.current) {
        clearInterval(updateCheckInterval.current);
      }
    };
  }, []);

  /**
   * Handle Service Worker updates
   */
  const handleSWUpdate = useCallback(() => {
    console.log('[usePWA] Service Worker update found');
    setHasUpdate(true);

    // Show update notification
    if ('Notification' in window && Notification.permission === 'granted') {
      new Notification('AutoSaham Update Available', {
        body: 'A new version is available. Refresh to update.',
        icon: '/icons/icon-192x192.png',
        tag: 'sw-update',
        requireInteraction: true
      });
    }
  }, []);

  /**
   * Handle messages from Service Worker
   */
  const handleSWMessage = useCallback((event) => {
    const { type, version } = event.data;

    if (type === 'SERVICE_WORKER_ACTIVATED') {
      console.log('[usePWA] Service Worker activated, version:', version);
      setHasUpdate(false);
    }
  }, []);

  /**
   * Detect online/offline status
   */
  useEffect(() => {
    const handleOnline = () => {
      console.log('[usePWA] Online status: ON');
      setIsOnline(true);

      // Attempt to sync pending trades when reconnected
      if ('serviceWorker' in navigator && 'SyncManager' in window) {
        navigator.serviceWorker.ready.then((reg) => {
          reg.sync?.register('sync-pending-trades').catch((error) => {
            console.warn('[usePWA] Background sync failed:', error);
          });
        });
      }
    };

    const handleOffline = () => {
      console.log('[usePWA] Online status: OFF');
      setIsOnline(false);
    };

    window.addEventListener('online', handleOnline);
    window.addEventListener('offline', handleOffline);

    return () => {
      window.removeEventListener('online', handleOnline);
      window.removeEventListener('offline', handleOffline);
    };
  }, []);

  /**
   * Handle beforeinstallprompt event
   */
  useEffect(() => {
    const handleBeforeInstallPrompt = (event) => {
      console.log('[usePWA] Install prompt triggered');
      event.preventDefault();

      // Check if already installed
      if (
        isStandaloneDisplayMode() ||
        window.navigator.standalone === true
      ) {
        setIsInstalled(true);
        return;
      }

      // Store the prompt for later
      setInstallPrompt(event);
      setInstallPromptShown(false);
    };

    const handleAppInstalled = () => {
      console.log('[usePWA] App installed');
      setIsInstalled(true);
      setInstallPrompt(null);

      // Show success notification
      if ('Notification' in window && Notification.permission === 'granted') {
        new Notification('AutoSaham Installed', {
          body: 'App installed successfully. You can now use it offline.',
          icon: '/icons/icon-192x192.png',
          tag: 'app-installed'
        });
      }
    };

    window.addEventListener('beforeinstallprompt', handleBeforeInstallPrompt);
    window.addEventListener('appinstalled', handleAppInstalled);

    // Check if app is already installed
    if (isStandaloneDisplayMode()) {
      setIsInstalled(true);
    }

    return () => {
      window.removeEventListener('beforeinstallprompt', handleBeforeInstallPrompt);
      window.removeEventListener('appinstalled', handleAppInstalled);
    };
  }, [isStandaloneDisplayMode]);

  /**
   * Open install prompt
   */
  const openInstallPrompt = useCallback(async () => {
    if (!installPrompt) {
      console.warn('[usePWA] Install prompt not available');
      return;
    }

    try {
      console.log('[usePWA] Showing install prompt');
      installPrompt.prompt();

      const { outcome } = await installPrompt.userChoice;
      console.log('[usePWA] Install prompt outcome:', outcome);

      if (outcome === 'accepted') {
        console.log('[usePWA] Installation accepted');
        setIsInstalled(true);
      } else {
        console.log('[usePWA] Installation declined');
      }

      setInstallPrompt(null);
      setInstallPromptShown(true);
    } catch (error) {
      console.error('[usePWA] Install prompt error:', error);
    }
  }, [installPrompt]);

  /**
   * Skip install prompt
   */
  const skipInstall = useCallback(() => {
    console.log('[usePWA] Skipping install');
    setInstallPrompt(null);

    // Remember choice for this session
    sessionStorage.setItem('skipInstallPrompt', 'true');
  }, []);

  /**
   * Alternative install method (if prompt not available)
   */
  const installApp = useCallback(async () => {
    if (installPrompt) {
      openInstallPrompt();
    } else {
      console.log('[usePWA] Install prompt not available, guiding user manually');

      const message = `
To install AutoSaham:

1. Open the menu (⋯) in your browser
2. Select "Install app" or "Add to Home Screen"
3. Confirm the installation

Supported browsers:
- Chrome/Edge: Menu → Install app
- Safari: Share → Add to Home Screen
- Firefox: Menu → Install
      `;

      alert(message);
    }
  }, [installPrompt, openInstallPrompt]);

  /**
   * Update app to latest version
   */
  const updateApp = useCallback(async () => {
    if (!swRegistration) {
      console.warn('[usePWA] Service Worker not registered');
      return;
    }

    try {
      setIsUpdating(true);
      console.log('[usePWA] Starting app update...');

      // Clear caches to force fresh download
      const cacheNames = await caches.keys();
      await Promise.all(
        cacheNames.map((name) => {
          if (name.includes('autosaham')) {
            console.log('[usePWA] Clearing cache:', name);
            return caches.delete(name);
          }
        })
      );

      // Unregister old SW and register new one
      await swRegistration.unregister();
      const newRegistration = await navigator.serviceWorker.register(
        SERVICE_WORKER_PATH,
        { scope: '/' }
      );

      setSWRegistration(newRegistration);
      setHasUpdate(false);

      console.log('[usePWA] Update complete, reloading...');

      // Reload page to get fresh content
      window.location.reload();
    } catch (error) {
      console.error('[usePWA] Update failed:', error);
      setIsUpdating(false);
    }
  }, [swRegistration]);

  /**
   * Request notification permission
   */
  const requestNotificationPermission = useCallback(async () => {
    if (!('Notification' in window)) {
      console.warn('[usePWA] Notifications not supported');
      return false;
    }

    if (Notification.permission === 'granted') {
      return true;
    }

    try {
      const permission = await Notification.requestPermission();
      console.log('[usePWA] Notification permission:', permission);
      return permission === 'granted';
    } catch (error) {
      console.error('[usePWA] Notification permission error:', error);
      return false;
    }
  }, []);

  /**
   * Send test notification
   */
  const sendTestNotification = useCallback(async () => {
    try {
      if (Notification.permission !== 'granted') {
        await requestNotificationPermission();
      }

      if ('serviceWorker' in navigator) {
        const registration = await navigator.serviceWorker.ready;

        const options = {
          body: 'This is a test notification from AutoSaham',
          icon: '/icons/icon-192x192.png',
          badge: '/icons/badge-72x72.png',
          tag: 'test-notification',
          data: {
            url: '/',
            timestamp: new Date().toISOString()
          }
        };

        registration.showNotification('AutoSaham Test', options);
        console.log('[usePWA] Test notification sent');
      }
    } catch (error) {
      console.error('[usePWA] Test notification error:', error);
    }
  }, [requestNotificationPermission]);

  return {
    // Status
    isInstalled,
    isOnline,
    hasUpdate,
    isUpdating,
    installPromptAvailable: installPrompt !== null && !installPromptShown,
    swRegistration,

    // Actions
    openInstallPrompt,
    skipInstall,
    installApp,
    updateApp,
    requestNotificationPermission,
    sendTestNotification,

    // Utilities
    installPrompt,
    setInstallPrompt
  };
};

export default usePWA;
