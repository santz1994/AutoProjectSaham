import { useEffect, useRef, useState, useCallback } from 'react'

export default function useWebSocket(path: string, onMessage?: (data: any) => void) {
  const wsRef = useRef<WebSocket | null>(null)
  const [status, setStatus] = useState<'idle' | 'connecting' | 'open' | 'closed' | 'error'>('idle')

  const send = useCallback((data: any) => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(typeof data === 'string' ? data : JSON.stringify(data))
    }
  }, [])

  useEffect(() => {
    const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
    const host = window.location.host
    const url = `${proto}://${host}${path}`
    setStatus('connecting')
    const ws = new WebSocket(url)
    wsRef.current = ws
    ws.onopen = () => setStatus('open')
    ws.onmessage = (ev) => {
      try {
        const d = JSON.parse(ev.data)
        onMessage && onMessage(d)
      } catch (e) {
        onMessage && onMessage(ev.data)
      }
    }
    ws.onclose = () => setStatus('closed')
    ws.onerror = () => setStatus('error')

    return () => {
      try {
        ws.close()
      } catch {}
    }
  }, [path, onMessage])

  return { send, status, wsRef }
}
