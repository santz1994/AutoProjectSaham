import React, { useEffect, useRef } from 'react'
import {
  createChart,
  ColorType,
  CrosshairMode,
  type Time,
  type UTCTimestamp,
  type SeriesMarker,
} from 'lightweight-charts'

type Candle = { time: string | number; open: number; high: number; low: number; close: number; volume?: number }
type Marker = { time: string | number; position?: 'aboveBar' | 'belowBar'; color?: string; shape?: 'arrowUp' | 'arrowDown' | 'circle' | 'square'; text?: string }

interface Props {
  data?: Candle[]
  markers?: Marker[]
  height?: number
}

function toChartTime(value: string | number): Time {
  if (typeof value === 'number') {
    const seconds = value > 1e12 ? Math.floor(value / 1000) : Math.floor(value)
    return seconds as UTCTimestamp
  }

  const parsed = Date.parse(value)
  if (!Number.isNaN(parsed)) {
    return Math.floor(parsed / 1000) as UTCTimestamp
  }

  return value as Time
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

    const formatted = data.map((d) => ({
      time: toChartTime(d.time),
      open: d.open,
      high: d.high,
      low: d.low,
      close: d.close,
    }))

    series.setData(formatted)

    if (markers && markers.length) {
      const m: SeriesMarker<Time>[] = markers.map((marker) => ({
        time: toChartTime(marker.time),
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
