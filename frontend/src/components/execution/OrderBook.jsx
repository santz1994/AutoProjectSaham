import React from 'react'
import { useTradingStore } from '../../store/useTradingStore'

export default function OrderBook() {
  const orderBook = useTradingStore((s) => s.orderBook)
  const bids = (orderBook && orderBook.bids) || []
  const asks = (orderBook && orderBook.asks) || []
  const volumes = [...bids.map((b) => b.volume), ...asks.map((a) => a.volume)]
  const maxVolume = volumes.length ? Math.max(...volumes) : 1

  return (
    <section className="card">
      <h2>Order Book</h2>
      <div style={{ fontSize: 12, fontFamily: 'monospace' }}>
        <div style={{ display: 'flex', flexDirection: 'column-reverse', gap: 4 }}>
          {asks.map((ask, i) => {
            const width = Math.round((ask.volume / maxVolume) * 100)
            return (
              <div key={`ask-${i}`} style={{ position: 'relative', padding: 6 }}>
                <div style={{ position: 'absolute', right: 0, top: 0, bottom: 0, background: 'rgba(255,0,0,0.06)', width: `${width}%` }} />
                <div style={{ position: 'relative', display: 'flex', justifyContent: 'space-between' }}>
                  <span style={{ color: '#f87171' }}>{ask.price}</span>
                  <span>{ask.volume}</span>
                </div>
              </div>
            )
          })}
        </div>

        <div style={{ textAlign: 'center', padding: '6px 0', fontWeight: 'bold', color: '#fff' }}>Spread</div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
          {bids.map((bid, i) => {
            const width = Math.round((bid.volume / maxVolume) * 100)
            return (
              <div key={`bid-${i}`} style={{ position: 'relative', padding: 6 }}>
                <div style={{ position: 'absolute', left: 0, top: 0, bottom: 0, background: 'rgba(0,255,0,0.06)', width: `${width}%` }} />
                <div style={{ position: 'relative', display: 'flex', justifyContent: 'space-between' }}>
                  <span style={{ color: '#34d399' }}>{bid.price}</span>
                  <span>{bid.volume}</span>
                </div>
              </div>
            )
          })}
        </div>
      </div>
    </section>
  )
}
