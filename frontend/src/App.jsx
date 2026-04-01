import React, { useState, useEffect } from 'react'
import Dashboard from './components/Dashboard'
import Login from './components/Login'
import './styles.css'
import useMarketFeed from './hooks/useMarketFeed'

export default function App() {
  const [user, setUser] = useState(null)

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
    <div className="app">
      <header className="app-header">
        <h1>AutoSaham Dashboard</h1>
      </header>
      <main>
        {user ? <div style={{ marginBottom: 12 }}>Signed in as {user}</div> : <Login onLogin={(u) => setUser(u)} />}
        <Dashboard />
      </main>
    </div>
  )
}
