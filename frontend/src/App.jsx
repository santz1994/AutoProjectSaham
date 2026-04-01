import React, { useState, useEffect } from 'react'
import Dashboard from './components/Dashboard'
import Login from './components/Login'
import PWAInstallButton from './components/PWAInstallButton'
import useMarketFeed from './hooks/useMarketFeed'
import useResponsive from './hooks/useResponsive'
import './styles.css'

export default function App() {
  const [user, setUser] = useState(null)
  const { cssVariables, darkMode, viewport } = useResponsive()

  // Register Service Worker on mount
  useEffect(() => {
    const registerServiceWorker = async () => {
      if (typeof window === 'undefined' || !('serviceWorker' in navigator)) return
      try {
        console.log('[App] Registering Service Worker...')
        const registration = await navigator.serviceWorker.register('/src/service-worker.js', { scope: '/' })
        console.log('[App] Service Worker registered successfully')
      } catch (error) {
        console.error('[App] Service Worker registration failed:', error)
      }
    }
    registerServiceWorker()
  }, [])

  // Setup manifest and theme meta tags
  useEffect(() => {
    if (typeof document === 'undefined') return

    // Add manifest
    const existingManifest = document.querySelector('link[rel="manifest"]')
    if (!existingManifest) {
      const manifestLink = document.createElement('link')
      manifestLink.rel = 'manifest'
      manifestLink.href = '/manifest.json'
      document.head.appendChild(manifestLink)
    }

    // Update theme color
    let themeColorMeta = document.querySelector('meta[name="theme-color"]')
    if (!themeColorMeta) {
      themeColorMeta = document.createElement('meta')
      themeColorMeta.name = 'theme-color'
      document.head.appendChild(themeColorMeta)
    }
    themeColorMeta.content = darkMode ? '#131722' : '#ffffff'

    // Set viewport meta for mobile
    let viewportMeta = document.querySelector('meta[name="viewport"]')
    if (!viewportMeta) {
      viewportMeta = document.createElement('meta')
      viewportMeta.name = 'viewport'
      document.head.appendChild(viewportMeta)
    }
    viewportMeta.content = 'width=device-width, initial-scale=1.0, viewport-fit=cover, user-scalable=yes'
  }, [darkMode])

  // Apply CSS variables
  useEffect(() => {
    if (typeof document === 'undefined') return
    const root = document.documentElement
    Object.entries(cssVariables).forEach(([key, value]) => {
      root.style.setProperty(key, value)
    })
    root.classList.toggle('dark-theme', darkMode)
    root.classList.toggle('light-theme', !darkMode)
  }, [cssVariables, darkMode])

  useEffect(() => {
    async function me() {
      const token = localStorage.getItem('token')
      if (!token) return
      try {
        const res = await fetch('/auth/me', { headers: { Authorization: `Bearer ${token}` } })
        if (!res.ok) return
        const j = await res.json()
        setUser(j.username)
      } catch (e) {
        // ignore
      }
    }
    me()
  }, [])

  // start market feed to populate live candles/orderbook
  useMarketFeed()

  return (
    <div className="app" style={cssVariables} data-theme={darkMode ? 'dark' : 'light'}>
      {/* PWA Install Button */}
      <PWAInstallButton variant="floating" position="bottom-right" />

      <header className="app-header">
        <h1>AutoSaham Dashboard</h1>
        <p style={{ margin: '4px 0', fontSize: '12px', opacity: 0.7 }}>Jakarta (WIB: UTC+7) | IDX Trading</p>
      </header>
      <main>
        {user ? <div style={{ marginBottom: 12 }}>Signed in as {user}</div> : <Login onLogin={(u) => setUser(u)} />}
        <Dashboard />
      </main>
    </div>
  )
}
