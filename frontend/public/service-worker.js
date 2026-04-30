/**
 * AutoSaham Service Worker
 * Provides offline support, intelligent caching, and background sync
 * 
 * Caching Strategy:
 * - Assets (HTML, CSS, JS): Cache-first with network fallback
 * - Images: Cache-first with network fallback (long TTL)
 * - API calls (charts, explainability): Network-first with cache fallback
 * - Market data: Network-first (always fresh)
 * - Third-party: Stale-while-revalidate
 */

const CACHE_VERSION = 'v3';
const APP_CACHE = `autosaham-app-${CACHE_VERSION}`;
const ASSETS_CACHE = `autosaham-assets-${CACHE_VERSION}`;
const API_CACHE = `autosaham-api-${CACHE_VERSION}`;
const IMAGE_CACHE = `autosaham-images-${CACHE_VERSION}`;
const IS_LOCAL_DEV = ['localhost', '127.0.0.1'].includes(self.location.hostname);

// Assets to cache on install (app shell)
const PRECACHE_URLS = [
  '/',
  '/index.html',
  '/manifest.json'
];

async function clearAutoSahamCaches() {
  const cacheNames = await caches.keys();
  await Promise.all(
    cacheNames
      .filter((name) => name.includes('autosaham'))
      .map((name) => caches.delete(name))
  );
}

/**
 * Service Worker Installation
 * Pre-cache essential app shell and assets
 */
self.addEventListener('install', (event) => {
  console.log('[SW] Service Worker installing...');

  if (IS_LOCAL_DEV) {
    self.skipWaiting();
    return;
  }
  
  event.waitUntil(
    caches.open(APP_CACHE).then((cache) => {
      console.log('[SW] Caching app shell');
      return cache.addAll(PRECACHE_URLS).catch((err) => {
        // Don't fail install if precache fails (some URLs might be dynamic)
        console.warn('[SW] Precache error (non-fatal):', err);
        return Promise.resolve();
      });
    })
  );
  
  // Force new service worker to activate immediately
  self.skipWaiting();
});

/**
 * Service Worker Activation
 * Clean up old caches
 */
self.addEventListener('activate', (event) => {
  console.log('[SW] Service Worker activating...');

  if (IS_LOCAL_DEV) {
    event.waitUntil(
      (async () => {
        await clearAutoSahamCaches();
        await self.registration.unregister();
      })()
    );
    return;
  }
  
  event.waitUntil(
    caches.keys().then((cacheNames) => {
      return Promise.all(
        cacheNames.map((cacheName) => {
          // Delete old cache versions
          if (
            cacheName !== APP_CACHE &&
            cacheName !== ASSETS_CACHE &&
            cacheName !== API_CACHE &&
            cacheName !== IMAGE_CACHE
          ) {
            console.log('[SW] Deleting old cache:', cacheName);
            return caches.delete(cacheName);
          }
        })
      );
    })
  );
  
  // Claim all clients immediately
  self.clients.matchAll().then((clients) => {
    clients.forEach((client) => {
      client.postMessage({
        type: 'SERVICE_WORKER_ACTIVATED',
        version: CACHE_VERSION
      });
    });
  });
});

/**
 * Fetch Event Handler
 * Implement intelligent caching strategies based on request type
 */
self.addEventListener('fetch', (event) => {
  if (IS_LOCAL_DEV) {
    return;
  }

  const { request } = event;
  const url = new URL(request.url);
  
  // Skip non-HTTP requests
  if (!url.protocol.startsWith('http')) {
    return;
  }

  // SKIP AUTH REQUESTS ENTIRELY - let them pass through without Service Worker interception
  // Auth requests must reach the actual backend at localhost:8000, not localhost:5173
  if (url.pathname.includes('/auth/')) {
    console.log('[SW] Skipping auth request (letting it pass through):', url.href);
    return; // Don't event.respondWith - let browser handle it
  }

  // Always prefer fresh HTML/app shell to avoid stale UI after deployments.
  if (request.mode === 'navigate') {
    event.respondWith(networkFirstStrategy(request, APP_CACHE, 3000));
    return;
  }
  
  // Determine caching strategy based on request
  if (isMarketDataRequest(url)) {
    // Market data: Always network-first (real-time requirement)
    event.respondWith(networkFirstStrategy(request, API_CACHE, 60000)); // 1 min cache
  } else if (isAPIRequest(url)) {
    // API calls: Network-first with fallback
    event.respondWith(networkFirstStrategy(request, API_CACHE));
  } else if (isImageRequest(url)) {
    // Images: Cache-first with network fallback
    event.respondWith(cacheFirstStrategy(request, IMAGE_CACHE, 7 * 24 * 60 * 60 * 1000)); // 7 days
  } else if (isAssetRequest(url)) {
    // Assets (CSS, JS): Cache-first with fallback
    event.respondWith(cacheFirstStrategy(request, ASSETS_CACHE, 24 * 60 * 60 * 1000)); // 1 day
  } else if (isThirdPartyRequest(url)) {
    // Third-party: Stale-while-revalidate
    event.respondWith(staleWhileRevalidateStrategy(request));
  } else {
    // Default: Network-first
    event.respondWith(networkFirstStrategy(request, API_CACHE));
  }
});

/**
 * Cache-First Strategy
 * Return from cache if available, fallback to network
 */
async function cacheFirstStrategy(request, cacheName, ttl = null) {
  try {
    const cache = await caches.open(cacheName);
    
    // Check cache first
    let response = await cache.match(request);
    
    if (response) {
      // Check if cached response is still valid (TTL)
      if (ttl) {
        const cacheDate = new Date(response.headers.get('date')).getTime();
        const now = Date.now();
        
        if (now - cacheDate > ttl) {
          console.log('[SW] Cache expired, fetching fresh:', request.url);
          // Fetch in background but return stale response
          fetchAndCache(request, cacheName);
        }
      }
      
      console.log('[SW] Cache hit:', request.url);
      return response;
    }
    
    // Not in cache, fetch from network
    console.log('[SW] Cache miss, fetching from network:', request.url);
    response = await fetch(request);
    
    // Cache successful responses
    if (response.ok && isCacheable(request)) {
      cache.put(request, response.clone());
    }
    
    return response;
  } catch (error) {
    console.error('[SW] Cache-first error:', error);
    // Return offline page if available
    return getOfflineResponse();
  }
}

/**
 * Network-First Strategy
 * Try network first, fallback to cache
 */
async function networkFirstStrategy(request, cacheName, timeoutMs = 5000) {
  const cache = await caches.open(cacheName);
  
  try {
    // Race: either get response or timeout
    const response = await Promise.race([
      fetch(request),
      new Promise((_, reject) =>
        setTimeout(() => reject(new Error('Network timeout')), timeoutMs)
      )
    ]);
    
    // Cache successful responses
    if (response.ok && isCacheable(request)) {
      cache.put(request, response.clone());
    }
    
    console.log('[SW] Network success:', request.url);
    return response;
  } catch (error) {
    console.log('[SW] Network failed, using cache:', request.url);
    
    // Fallback to cache
    const cachedResponse = await cache.match(request);
    if (cachedResponse) {
      return cachedResponse;
    }
    
    // Return offline response
    return getOfflineResponse();
  }
}

/**
 * Stale-While-Revalidate Strategy
 * Return cached response immediately, update in background
 */
async function staleWhileRevalidateStrategy(request) {
  const cache = await caches.open(API_CACHE);
  const cachedResponse = await cache.match(request);
  
  const fetchPromise = fetch(request).then((response) => {
    if (response.ok && isCacheable(request)) {
      cache.put(request, response.clone());
    }
    return response;
  });
  
  return cachedResponse || fetchPromise;
}

/**
 * Helper: Fetch and cache in background
 */
async function fetchAndCache(request, cacheName) {
  try {
    const response = await fetch(request);
    if (response.ok && isCacheable(request)) {
      const cache = await caches.open(cacheName);
      cache.put(request, response.clone());
    }
  } catch (error) {
    console.warn('[SW] Background fetch failed:', error);
  }
}

/**
 * Helper: Determine if request is for market data
 */
function isMarketDataRequest(url) {
  return (
    url.pathname.includes('/api/charts/') ||
    url.pathname.includes('/api/market-data/') ||
    url.pathname.includes('/ws/charts/')
  );
}

/**
 * Helper: Determine if request is for API
 */
function isAPIRequest(url) {
  return url.pathname.startsWith('/api/');
}

/**
 * Helper: Determine if request is for image
 */
function isImageRequest(url) {
  return /\.(png|jpg|jpeg|svg|webp|gif|ico)$/i.test(url.pathname);
}

/**
 * Helper: Determine if request is for asset (CSS, JS, fonts)
 */
function isAssetRequest(url) {
  return /\.(js|css|woff|woff2|ttf|otf|eot)$/i.test(url.pathname) ||
         url.pathname.endsWith('.jsx') ||
         url.pathname.endsWith('.css');
}

/**
 * Helper: Determine if request is third-party
 */
function isThirdPartyRequest(url) {
  return !url.hostname.includes(self.location.hostname);
}

/**
 * Helper: Check if response is cacheable
 */
function isCacheable(request) {
  // Only cache GET requests
  if (request.method !== 'GET') {
    return false;
  }
  
  // Don't cache logout or sensitive endpoints
  if (
    request.url.includes('/logout') ||
    request.url.includes('/auth/') ||
    request.url.includes('/api/health')
  ) {
    return false;
  }
  
  return true;
}

/**
 * Helper: Get offline response
 */
async function getOfflineResponse() {
  try {
    const cache = await caches.open(APP_CACHE);
    return await cache.match('/index.html') || new Response('Offline', { status: 503 });
  } catch (error) {
    return new Response('Offline', { status: 503 });
  }
}

/**
 * Background Sync Handler
 * Sync pending trades when connection restored
 */
self.addEventListener('sync', (event) => {
  console.log('[SW] Background sync event:', event.tag);
  
  if (event.tag === 'sync-pending-trades') {
    event.waitUntil(syncPendingTrades());
  }
});

/**
 * Sync pending trades to server
 */
async function syncPendingTrades() {
  try {
    const db = await openDB();
    const pendingTrades = await getAllPendingTrades(db);
    
    for (const trade of pendingTrades) {
      try {
        const response = await fetch('/api/trades/pending', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(trade)
        });
        
        if (response.ok) {
          await removePendingTrade(db, trade.id);
          console.log('[SW] Synced trade:', trade.id);
        }
      } catch (error) {
        console.error('[SW] Failed to sync trade:', error);
        // Retry later
        throw error;
      }
    }
  } catch (error) {
    console.error('[SW] Sync failed:', error);
    throw error; // Retry sync later
  }
}

/**
 * Push Notification Handler
 * Handle trading alerts and market updates
 */
self.addEventListener('push', (event) => {
  console.log('[SW] Push notification received');
  
  if (!event.data) {
    return;
  }
  
  try {
    const data = event.data.json();
    const options = {
      body: data.message,
      icon: '/icons/icon-192x192.png',
      badge: '/icons/badge-72x72.png',
      tag: data.tag || 'autosaham-notification',
      requireInteraction: data.requireInteraction || false,
      data: {
        url: data.url || '/',
        timestamp: new Date().toISOString()
      },
      actions: [
        {
          action: 'open',
          title: 'Open',
          icon: '/icons/action-open.png'
        },
        {
          action: 'close',
          title: 'Close',
          icon: '/icons/action-close.png'
        }
      ]
    };
    
    // Add color and image for rich notifications
    if (data.type === 'BUY') {
      options.badge = '/icons/badge-buy.png';
      options.tag = 'trading-alert-buy';
    } else if (data.type === 'SELL') {
      options.badge = '/icons/badge-sell.png';
      options.tag = 'trading-alert-sell';
    }
    
    event.waitUntil(
      self.registration.showNotification(data.title || 'AutoSaham', options)
    );
  } catch (error) {
    console.error('[SW] Push notification error:', error);
  }
});

/**
 * Notification Click Handler
 */
self.addEventListener('notificationclick', (event) => {
  console.log('[SW] Notification clicked:', event.action);
  
  event.notification.close();
  
  if (event.action === 'close') {
    return;
  }
  
  const url = event.notification.data?.url || '/';
  
  event.waitUntil(
    clients.matchAll({ type: 'window' }).then((clientList) => {
      // Check if window already open
      for (const client of clientList) {
        if (client.url === url && 'focus' in client) {
          return client.focus();
        }
      }
      
      // Open new window
      if (clients.openWindow) {
        return clients.openWindow(url);
      }
    })
  );
});

/**
 * Process IndexedDB for offline data persistance
 * Note: Full implementation depends on client side
 */
async function openDB() {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open('autosaham', 1);
    request.onerror = () => reject(request.error);
    request.onsuccess = () => resolve(request.result);
  });
}

async function getAllPendingTrades(db) {
  return new Promise((resolve, reject) => {
    const transaction = db.transaction(['pendingTrades'], 'readonly');
    const store = transaction.objectStore('pendingTrades');
    const request = store.getAll();
    request.onerror = () => reject(request.error);
    request.onsuccess = () => resolve(request.result);
  });
}

async function removePendingTrade(db, tradeId) {
  return new Promise((resolve, reject) => {
    const transaction = db.transaction(['pendingTrades'], 'readwrite');
    const store = transaction.objectStore('pendingTrades');
    const request = store.delete(tradeId);
    request.onerror = () => reject(request.error);
    request.onsuccess = () => resolve();
  });
}

console.log('[SW] Service Worker loaded (version:', CACHE_VERSION, ')');
