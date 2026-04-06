import React, { useState, useEffect } from 'react'
// Enhanced Components
import NavbarEnhanced from './components/NavbarEnhanced'
import SidebarEnhanced from './components/SidebarEnhanced'
import ToastContainer from './components/Toast'
import ErrorBoundary from './components/ErrorBoundary'
import { LoadingOverlay } from './components/LoadingSkeletons'
// Page Components
import DashboardPage from './components/DashboardPage'
import MarketIntelligencePage from './components/MarketIntelligencePage'
import StrategiesPage from './components/StrategiesPage'
import TradeLogsPage from './components/TradeLogsPage'
import SettingsPage from './components/SettingsPage'
import Login from './components/Login'
import Register from './components/Register'
import ForgotPassword from './components/ForgotPassword'
import PWAInstallButton from './components/PWAInstallButton'
// Hooks and Utilities
import useMarketFeed from './hooks/useMarketFeed'
import useResponsive from './hooks/useResponsive'
import useTradingStore from './store/tradingStore'
import AuthService from './utils/authService'
import toast from './store/toastStore'
// Styles
import './styles.css'
import './styles/navbar-enhanced.css'
import './styles/sidebar-enhanced.css'
import './styles/dashboard.css'
import './styles/market.css'
import './styles/strategies.css'
import './styles/tradelogs.css'
import './styles/settings.css'

export default function App() {
  const [user, setUser] = useState(null)
  const [currentPage, setCurrentPage] = useState('dashboard')
  const [authPage, setAuthPage] = useState('login') // 'login', 'register', 'forgot-password'
  const [isInitializing, setIsInitializing] = useState(true)
  const { cssVariables, darkMode, viewport } = useResponsive()
  const killSwitchTriggered = useTradingStore((s) => s.killSwitchTriggered)

  // Register Service Worker on mount
  useEffect(() => {
    // DISABLED: Service Worker causing update loop and session issues
    // Re-enable in production after fixing authentication persistence
    
    /* COMMENTED OUT - CAUSING LOGIN LOOP
    const registerServiceWorker = async () => {
      if (typeof window === 'undefined' || !('serviceWorker' in navigator)) return
      try {
        console.log('[App] Registering Service Worker...')
        // Service Worker in public/ can register root scope
        const registration = await navigator.serviceWorker.register('/service-worker.js', {
          scope: '/',
        })
        console.log('[App] Service Worker registered successfully')
        toast.success('App is ready to work offline', { duration: 3000 })
      } catch (error) {
        console.error('[App] Service Worker registration failed:', error)
        toast.warning('Offline mode unavailable', { duration: 3000 })
      }
    }
    registerServiceWorker()
    */
    
    // Unregister any existing service workers to clear the update loop
    if ('serviceWorker' in navigator) {
      navigator.serviceWorker.getRegistrations().then((registrations) => {
        registrations.forEach((registration) => {
          console.log('[App] Unregistering service worker to fix update loop')
          registration.unregister()
        })
      })
    }
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

  // SECURITY FIX: Check auth status on mount using secure httpOnly cookies
  useEffect(() => {
    async function checkAuth() {
      try {
        setIsInitializing(true)
        const userInfo = await AuthService.getMe()
        if (userInfo && userInfo.username) {
          setUser(userInfo.username)
          toast.success(`Welcome back, ${userInfo.username}!`, { duration: 3000 })
        }
      } catch (error) {
        console.log('Auth check failed:', error.message)
        // User not logged in yet, redirect to login
      } finally {
        setIsInitializing(false)
      }
    }
    checkAuth()
  }, [])

  // Start market feed to populate live candles/orderbook
  useMarketFeed()

  // Handle login with toast notification
  const handleLogin = (username) => {
    setUser(username)
    setAuthPage('login') // Reset auth page
    toast.success(`Welcome, ${username}!`, { duration: 3000 })
  }

  // Handle page navigation
  const handleNavigate = (page) => {
    setCurrentPage(page)
  }

  // Show loading overlay during initialization
  if (isInitializing) {
    return <LoadingOverlay message="Initializing AutoSaham..." />
  }

  // Show authentication pages if not authenticated
  if (!user) {
    return (
      <ErrorBoundary>
        {authPage === 'login' && (
          <Login
            onLogin={handleLogin}
            onSwitchToRegister={() => setAuthPage('register')}
            onSwitchToForgotPassword={() => setAuthPage('forgot-password')}
          />
        )}
        {authPage === 'register' && (
          <Register
            onSuccess={handleLogin}
            onSwitchToLogin={() => setAuthPage('login')}
          />
        )}
        {authPage === 'forgot-password' && (
          <ForgotPassword
            onSwitchToLogin={() => setAuthPage('login')}
          />
        )}
        <ToastContainer />
      </ErrorBoundary>
    )
  }

  // Render page with error boundary
  const renderPage = () => {
    switch (currentPage) {
      case 'dashboard':
        return <ErrorBoundary><DashboardPage /></ErrorBoundary>
      case 'market':
        return <ErrorBoundary><MarketIntelligencePage /></ErrorBoundary>
      case 'strategies':
        return <ErrorBoundary><StrategiesPage /></ErrorBoundary>
      case 'trades':
        return <ErrorBoundary><TradeLogsPage /></ErrorBoundary>
      case 'settings':
        return <ErrorBoundary><SettingsPage /></ErrorBoundary>
      default:
        return <ErrorBoundary><DashboardPage /></ErrorBoundary>
    }
  }

  return (
    <ErrorBoundary>
      <div className="app-container" style={cssVariables} data-theme={darkMode ? 'dark' : 'light'}>
        {/* Enhanced Navigation Bar */}
        <NavbarEnhanced />

        <div className="app-layout">
          {/* Enhanced Sidebar */}
          <SidebarEnhanced currentPage={currentPage} onNavigate={handleNavigate} />

          {/* Main Content with Error Boundaries */}
          <main className="app-main" role="main">
            {renderPage()}
          </main>
        </div>

        {/* PWA Install Button */}
        <PWAInstallButton variant="floating" position="bottom-right" />

        {/* Toast Notification Container */}
        <ToastContainer />
      </div>
    </ErrorBoundary>
  )
}
