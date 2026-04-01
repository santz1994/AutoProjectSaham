import React, { useEffect, useRef } from 'react'
import { createChart, ColorType, CrosshairMode } from 'lightweight-charts'

type Candle = { time: string | number; open: number; high: number; low: number; close: number; volume?: number }
type Marker = { time: string | number; position?: 'aboveBar' | 'belowBar'; color?: string; shape?: 'arrowUp' | 'arrowDown' | 'circle' | 'square'; text?: string }

interface Props {
  data?: Candle[]
  markers?: Marker[]
  height?: number
}

export default function CandlestickChart({ data = [], markers = [], height = 360 }: Props) {
  const ref = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    if (!ref.current) return

    const chart = createChart(ref.current, {
      width: ref.current.clientWidth,
      height,
      layout: { background: { type: ColorType.Solid, color: '#0f1720' }, textColor: '#e6eef6' },
      grid: { vertLines: { color: '#1f2937' }, horzLines: { color: '#1f2937' } },
      crosshair: { mode: CrosshairMode.Normal },
    })

    const series = chart.addCandlestickSeries({
      upColor: '#26a69a',
      downColor: '#ef5350',
      wickUpColor: '#26a69a',
      wickDownColor: '#ef5350',
      borderVisible: false,
    })

    const formatted = data.map((d) => {
      const time = typeof d.time === 'number' ? Math.floor(d.time / 1000) : d.time
      return { time, open: d.open, high: d.high, low: d.low, close: d.close }
    })

    series.setData(formatted)

    if (markers && markers.length) {
      const m = markers.map((marker) => ({
        time: typeof marker.time === 'number' ? Math.floor(marker.time / 1000) : marker.time,
        position: marker.position || 'belowBar',
        color: marker.color || (marker.position === 'aboveBar' ? '#FF9800' : '#2196F3'),
        shape: marker.shape || (marker.position === 'aboveBar' ? 'arrowDown' : 'arrowUp'),
        text: marker.text || '',
      }))
      series.setMarkers(m)
    }

    const ro = new ResizeObserver(() => {
      if (ref.current) {
        chart.applyOptions({ width: ref.current.clientWidth })
      }
    })
    ro.observe(ref.current)

    return () => {
      ro.disconnect()
      chart.remove()
    }
  }, [data, markers, height])

  return <div ref={ref} style={{ width: '100%', height, minHeight: 200 }} />
}
