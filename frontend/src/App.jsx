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
import ProfilePage from './components/ProfilePage'
import AIMonitorPage from './components/AIMonitorPage'
import AIGraphPage from './components/AIGraphPage'
import Login from './components/Login'
import Register from './components/Register'
import ForgotPassword from './components/ForgotPassword'
import PWAInstallButton from './components/PWAInstallButton'
// Hooks and Utilities
import startMarketFeed from './hooks/useMarketFeed'
import useResponsive from './hooks/useResponsive'
import apiService from './utils/apiService'
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
import './styles/profile.css'
import './styles/ai-monitor.css'
import './styles/ai-graph.css'

export default function App() {
  const [user, setUser] = useState(null)
  const [currentPage, setCurrentPage] = useState('dashboard')
  const [authPage, setAuthPage] = useState('login') // 'login', 'register', 'forgot-password'
  const [isInitializing, setIsInitializing] = useState(true)
  const [themePreference, setThemePreference] = useState(() => {
    if (typeof window === 'undefined') return 'auto'
    return localStorage.getItem('autosaham.theme') || 'auto'
  })
  const { cssVariables, darkMode: systemDarkMode } = useResponsive()
  const darkMode = themePreference === 'dark'
    ? true
    : themePreference === 'light'
      ? false
      : systemDarkMode

  const applyThemePreference = (nextTheme) => {
    const allowedThemes = ['dark', 'light', 'auto']
    const safeTheme = allowedThemes.includes(nextTheme) ? nextTheme : 'auto'
    setThemePreference(safeTheme)
    if (typeof window !== 'undefined') {
      localStorage.setItem('autosaham.theme', safeTheme)
      window.dispatchEvent(new Event('autosaham:theme-changed'))
    }
  }

  // Register Service Worker on mount
  useEffect(() => {
    if (typeof window === 'undefined' || !('serviceWorker' in navigator)) return

    const isLocalHost = ['localhost', '127.0.0.1'].includes(window.location.hostname)
    const isTestMode = import.meta?.env?.MODE === 'test'

    // Local dev only: clear stale workers/caches once so UI always reflects latest code.
    if (!isLocalHost || isTestMode) {
      return
    }

    navigator.serviceWorker.getRegistrations().then((registrations) => {
      registrations.forEach((registration) => {
        registration.unregister()
      })
    }).catch(() => {
      // Non-blocking cleanup.
    })

    if ('caches' in window && typeof caches.keys === 'function') {
      caches.keys().then((cacheNames) => {
        cacheNames.forEach((cacheName) => {
          if (cacheName.includes('autosaham')) {
            caches.delete(cacheName)
          }
        })
      }).catch(() => {
        // Non-blocking cleanup.
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

  // Listen for theme updates coming from settings page.
  useEffect(() => {
    if (typeof window === 'undefined') return

    const syncThemePreferenceFromStorage = () => {
      const nextTheme = localStorage.getItem('autosaham.theme') || 'auto'
      setThemePreference(nextTheme)
    }

    syncThemePreferenceFromStorage()
    window.addEventListener('autosaham:theme-changed', syncThemePreferenceFromStorage)
    window.addEventListener('storage', syncThemePreferenceFromStorage)

    return () => {
      window.removeEventListener('autosaham:theme-changed', syncThemePreferenceFromStorage)
      window.removeEventListener('storage', syncThemePreferenceFromStorage)
    }
  }, [])

  // SECURITY FIX: Check auth status on mount using secure httpOnly cookies
  useEffect(() => {
    async function checkAuth() {
      try {
        setIsInitializing(true)
        const userInfo = await AuthService.getMe()
        if (userInfo && userInfo.username) {
          setUser(userInfo.username)
          try {
            const userSettings = await apiService.getUserSettings()
            const localTheme = typeof window !== 'undefined'
              ? localStorage.getItem('autosaham.theme')
              : null
            const preferredTheme = localTheme || userSettings?.theme || 'auto'
            applyThemePreference(preferredTheme)
          } catch {
            // Keep default theme preference when settings API is unavailable.
          }
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

  // Start market feed once after mount and clean up on unmount.
  useEffect(() => {
    const stopFeed = startMarketFeed()
    return () => {
      if (typeof stopFeed === 'function') {
        stopFeed()
      }
    }
  }, [])

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

  const handleLogout = () => {
    setUser(null)
    setCurrentPage('dashboard')
    setAuthPage('login')
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
        return <ErrorBoundary><DashboardPage onNavigate={handleNavigate} /></ErrorBoundary>
      case 'market':
        return <ErrorBoundary><MarketIntelligencePage theme={darkMode ? 'dark' : 'light'} /></ErrorBoundary>
      case 'strategies':
        return <ErrorBoundary><StrategiesPage /></ErrorBoundary>
      case 'trades':
        return <ErrorBoundary><TradeLogsPage /></ErrorBoundary>
      case 'profile':
        return <ErrorBoundary><ProfilePage onNavigate={handleNavigate} /></ErrorBoundary>
      case 'ai-monitor':
        return <ErrorBoundary><AIMonitorPage onNavigate={handleNavigate} /></ErrorBoundary>
      case 'ai-graph':
        return <ErrorBoundary><AIGraphPage theme={darkMode ? 'dark' : 'light'} /></ErrorBoundary>
      case 'settings':
        return (
          <ErrorBoundary>
            <SettingsPage
              onLogout={handleLogout}
              currentThemePreference={themePreference}
              onThemePreferenceChange={applyThemePreference}
            />
          </ErrorBoundary>
        )
      default:
        return <ErrorBoundary><DashboardPage /></ErrorBoundary>
    }
  }

  return (
    <ErrorBoundary>
      <div className="app-container" style={cssVariables} data-theme={darkMode ? 'dark' : 'light'}>
        {/* Enhanced Navigation Bar */}
        <NavbarEnhanced
          user={user}
          onLogout={handleLogout}
          onNavigate={handleNavigate}
          currentThemePreference={themePreference}
          onThemePreferenceChange={applyThemePreference}
        />

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
