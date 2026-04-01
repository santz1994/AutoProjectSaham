import React, { useEffect, useState, useMemo } from 'react'
import { Line } from 'react-chartjs-2'
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend
} from 'chart.js'
ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Title, Tooltip, Legend)
import CandlestickChart from './charts/CandlestickChart'
import { useTradingStore } from '../store/useTradingStore'

export default function Portfolio() {
  const [data, setData] = useState(null)

  useEffect(() => {
    fetch('/api/portfolio')
      .then(r => r.json())
      .then(j => setData(j.portfolio))
      .catch(() => setData(null))
  }, [])

  const chartData = {
    labels: ['Start', 'Now'],
    datasets: [
      {
        label: 'Balance',
        data: data && data.snapshot ? [0, data.snapshot.balance] : [0, 0],
        borderColor: 'rgba(75,192,192,1)',
        backgroundColor: 'rgba(75,192,192,0.2)'
      }
    ]
  }

  const sampleCandles = useMemo(() => {
    const now = Date.now()
    let price = data && data.snapshot && data.snapshot.balance ? Number(data.snapshot.balance) : 100
    const candles = []
    for (let i = 50; i > 0; i--) {
      const t = now - i * 60 * 1000
      const o = price + (Math.random() - 0.5) * 2
      const c = o + (Math.random() - 0.5) * 2
      const h = Math.max(o, c) + Math.random() * 1.5
      const l = Math.min(o, c) - Math.random() * 1.5
      candles.push({ time: Math.floor(t / 1000), open: Number(o.toFixed(2)), high: Number(h.toFixed(2)), low: Number(l.toFixed(2)), close: Number(c.toFixed(2)) })
      price = c
    }
    return candles
  }, [data])

  const markers = useTradingStore((s) => s.markers)

  return (
    <section className="card">
      <h2>Portfolio</h2>
      {data ? (
        <div>
          <p>Cash: {data.snapshot ? data.snapshot.cash : '-'}</p>
          <p>Positions: {JSON.stringify(data.snapshot ? data.snapshot.positions : {})}</p>
          <div style={{ height: 240 }}>
                <Line data={chartData} />
          </div>
              <div style={{ marginTop: 12 }}>
                <h3>Price (sample)</h3>
                <CandlestickChart data={sampleCandles} markers={markers} height={260} />
              </div>
        </div>
      ) : (
        <p>Loading portfolio...</p>
      )}
    </section>
  )
}
