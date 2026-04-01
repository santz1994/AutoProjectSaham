import React, { useState } from 'react'

export default function OrderEntryForm({ onSubmit }) {
  const [symbol, setSymbol] = useState('IDX:BBCA')
  const [side, setSide] = useState('BUY')
  const [type, setType] = useState('MARKET')
  const [price, setPrice] = useState('')
  const [qty, setQty] = useState(1)
  const [status, setStatus] = useState(null)

  async function handleSubmit(e) {
    e.preventDefault()
    const body = { symbol, side, type, price: price ? Number(price) : null, qty: Number(qty) }
    setStatus('sending')
    try {
      const res = await fetch('/api/orders', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      if (res.ok) {
        const j = await res.json().catch(() => ({}))
        setStatus('ok')
        onSubmit && onSubmit(j)
      } else {
        const t = await res.text().catch(() => '')
        setStatus(`err: ${res.status} ${t}`)
      }
    } catch (err) {
      setStatus('network error')
    }
    setTimeout(() => setStatus(null), 3000)
  }

  return (
    <form onSubmit={handleSubmit} style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 8 }}>
      <input value={symbol} onChange={(e) => setSymbol(e.target.value)} />
      <select value={side} onChange={(e) => setSide(e.target.value)}>
        <option>BUY</option>
        <option>SELL</option>
      </select>
      <select value={type} onChange={(e) => setType(e.target.value)}>
        <option>MARKET</option>
        <option>LIMIT</option>
      </select>
      {type === 'LIMIT' ? (
        <input placeholder="price" value={price} onChange={(e) => setPrice(e.target.value)} />
      ) : null}
      <input type="number" value={qty} onChange={(e) => setQty(e.target.value)} style={{ width: 80 }} />
      <button type="submit">Send</button>
      {status ? <span style={{ marginLeft: 8 }}>{status}</span> : null}
    </form>
  )
}
