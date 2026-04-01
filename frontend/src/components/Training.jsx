import React, { useEffect, useState } from 'react'

export default function Training() {
  const [runs, setRuns] = useState(null)

  useEffect(() => {
    fetch('/api/training')
      .then(r => r.json())
      .then(j => setRuns(j.runs))
      .catch(() => setRuns([]))
  }, [])

  return (
    <section className="card">
      <h2>Training</h2>
      {runs && runs.length ? (
        <ul>
          {runs.map((r, i) => (
            <li key={i}>{JSON.stringify(r)}</li>
          ))}
        </ul>
      ) : (
        <p>No training runs found (placeholder).</p>
      )}
    </section>
  )
}
