import React, { useEffect, useState } from 'react'
import useWebSocket from '../hooks/useWebSocket'

export default function Events() {
  const [events, setEvents] = useState([])
  useWebSocket('/ws/events', (d) => setEvents((s) => [d, ...s].slice(0, 100)))

  return (
    <section className="card">
      <h2>Events (live)</h2>
      <div className="event-list">
        {events.length === 0 ? <p>No events yet.</p> : events.map((ev, i) => (
          <pre key={i} className="event-item">{JSON.stringify(ev)}</pre>
        ))}
      </div>
    </section>
  )
}
