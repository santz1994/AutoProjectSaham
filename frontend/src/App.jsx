import React, { useState, useEffect } from 'react'
import Navbar from './components/Navbar'
import Sidebar from './components/Sidebar'
import DashboardPage from './components/DashboardPage'
import MarketIntelligencePage from './components/MarketIntelligencePage'
import StrategiesPage from './components/StrategiesPage'
import TradeLogsPage from './components/TradeLogsPage'
import SettingsPage from './components/SettingsPage'
import Login from './components/Login'
import PWAInstallButton from './components/PWAInstallButton'
import useMarketFeed from './hooks/useMarketFeed'
import useResponsive from './hooks/useResponsive'
import useTradingStore from './store/tradingStore'
import './styles.css'
import './styles/navbar.css'
import './styles/sidebar.css'
import './styles/dashboard.css'
import './styles/market.css'
import './styles/strategies.css'
import './styles/tradelogs.css'
import './styles/settings.css'

export default function App() {
  const [user, setUser] = useState(null)
  const [currentPage, setCurrentPage] = useState('dashboard')
  const { cssVariables, darkMode, viewport } = useResponsive()
  const killSwitchTriggered = useTradingStore((s) => s.killSwitchTriggered)

  // Register Service Worker on mount
  useEffect(() => {
    const registerServiceWorker = async () => {
      if (typeof window === 'undefined' || !('serviceWorker' in navigator)) return
      try {
        console.log('[App] Registering Service Worker...')
        // Use Service-Worker-Allowed header to allow scope at root
        const registration = await navigator.serviceWorker.register('/src/service-worker.js', {
          scope: './',
        })
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
    themeColorMeta.content = darkMode ? '#0a0e27' : '#f1f5f9'

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

  // Start market feed to populate live candles/orderbook
  useMarketFeed()

  if (!user) {
    return (
      <div className="auth-container">
        <Login onLogin={(u) => setUser(u)} />
      </div>
    )
  }

  return (
    <div className="app-container" style={cssVariables} data-theme={darkMode ? 'dark' : 'light'}>
      {/* Navigation Bar */}
      <Navbar />

      <div className="app-layout">
        {/* Sidebar */}
        <Sidebar currentPage={currentPage} onNavigate={setCurrentPage} />

        {/* Main Content */}
        <main className="app-main">
          {currentPage === 'dashboard' && <DashboardPage />}
          {currentPage === 'market' && <MarketIntelligencePage />}
          {currentPage === 'strategies' && <StrategiesPage />}
          {currentPage === 'trades' && <TradeLogsPage />}
          {currentPage === 'settings' && <SettingsPage />}
        </main>
      </div>

      {/* PWA Install Button */}
      <PWAInstallButton variant="floating" position="bottom-right" />
    </div>
  )
}
