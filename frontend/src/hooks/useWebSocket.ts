import { useEffect, useRef, useState, useCallback } from 'react'

function getApiBaseUrl(): string {
  const envApiUrl = (import.meta as any)?.env?.VITE_API_URL as string | undefined
  if (envApiUrl) return envApiUrl.replace(/\/+$/, '')
  if (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1') {
    return `${window.location.protocol}//localhost:8000`
  }
  return `${window.location.protocol}//${window.location.host}`
}

async function fetchWsToken(): Promise<string | null> {
  try {
      const resp = await fetch(`${getApiBaseUrl()}/auth/ws-token`, {
      method: 'GET',
      credentials: 'include',
    })
    if (!resp.ok) return null
    const data = await resp.json()
    return data?.token || null
  } catch {
    return null
  }
}

export default function useWebSocket(path: string, onMessage?: (data: any) => void) {
  const wsRef = useRef<WebSocket | null>(null)
  const onMessageRef = useRef(onMessage)
  const [status, setStatus] = useState<'idle' | 'connecting' | 'open' | 'closed' | 'error'>('idle')

  // Keep the callback ref in sync when it changes
  useEffect(() => {
    onMessageRef.current = onMessage
  }, [onMessage])

  const send = useCallback((data: any) => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(typeof data === 'string' ? data : JSON.stringify(data))
    }
  }, [])

  useEffect(() => {
    let cancelled = false

    const connect = async () => {
      const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
      const envApiUrl = (import.meta as any)?.env?.VITE_API_URL as string | undefined
      let backendHost = window.location.host
      if (envApiUrl) {
        try {
          backendHost = new URL(envApiUrl).host
        } catch {
          backendHost = window.location.host
        }
      } else if (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1') {
        backendHost = 'localhost:8000'
      }

      const token = await fetchWsToken()
      if (cancelled) return

      const qs = token ? `?token=${encodeURIComponent(token)}` : ''
      const url = `${proto}://${backendHost}${path}${qs}`
      setStatus('connecting')

      console.log(`[useWebSocket] Connecting to ${url}`)
      const ws = new WebSocket(url)
      wsRef.current = ws

      ws.onopen = () => {
        console.log(`[useWebSocket] Connected to ${path}`)
        setStatus('open')
      }

      ws.onmessage = (ev) => {
        try {
          const d = JSON.parse(ev.data)
          onMessageRef.current && onMessageRef.current(d)
        } catch (e) {
          onMessageRef.current && onMessageRef.current(ev.data)
        }
      }

      ws.onclose = () => {
        console.log(`[useWebSocket] Disconnected from ${path}`)
        setStatus('closed')
      }

      ws.onerror = (error) => {
        console.error(`[useWebSocket] Error on ${path}:`, error)
        setStatus('error')
      }
    }

    connect()

    return () => {
      cancelled = true
      try {
        console.log(`[useWebSocket] Closing connection to ${path}`)
        if (wsRef.current) {
          wsRef.current.close()
        }
      } catch {}
    }
  }, [path])

  return { send, status, wsRef }
}