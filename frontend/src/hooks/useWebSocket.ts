import { useEffect, useRef, useState, useCallback } from 'react'

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
      // For local dev, route WebSocket to backend FastAPI server
      backendHost = 'localhost:8000'
    }
    const url = `${proto}://${backendHost}${path}`
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

    return () => {
      try {
        console.log(`[useWebSocket] Closing connection to ${path}`)
        ws.close()
      } catch {}
    }
  }, [path])

  return { send, status, wsRef }
}
