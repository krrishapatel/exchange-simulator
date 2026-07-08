import React, { useRef, useEffect } from 'react'

const BUCKETS = [
  { label: '<100ns', min: 0, max: 100 },
  { label: '100-200ns', min: 100, max: 200 },
  { label: '200-500ns', min: 200, max: 500 },
  { label: '500ns-1us', min: 500, max: 1000 },
  { label: '1-5us', min: 1000, max: 5000 },
  { label: '>5us', min: 5000, max: Infinity },
]

function formatNs(ns) {
  if (ns == null) return '--'
  if (ns < 1000) return `${ns}ns`
  if (ns < 1000000) return `${(ns / 1000).toFixed(1)}us`
  return `${(ns / 1000000).toFixed(2)}ms`
}

export default function LatencyPanel({ latency }) {
  const canvasRef = useRef(null)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas || !latency) return

    const ctx = canvas.getContext('2d')
    const dpr = window.devicePixelRatio || 1
    const width = canvas.clientWidth
    const height = canvas.clientHeight
    canvas.width = width * dpr
    canvas.height = height * dpr
    ctx.scale(dpr, dpr)

    // Clear
    ctx.clearRect(0, 0, width, height)

    // Compute bucket counts from percentile data (approximate distribution)
    // We use the stats to estimate a distribution shape
    const stats = latency
    const bucketCounts = estimateBucketCounts(stats)
    const maxCount = Math.max(...bucketCounts, 1)

    const barPadding = 4
    const chartLeft = 10
    const chartRight = width - 10
    const chartTop = 10
    const chartBottom = height - 24
    const chartWidth = chartRight - chartLeft
    const chartHeight = chartBottom - chartTop
    const barWidth = (chartWidth - barPadding * (BUCKETS.length - 1)) / BUCKETS.length

    // Draw bars
    for (let i = 0; i < BUCKETS.length; i++) {
      const x = chartLeft + i * (barWidth + barPadding)
      const barHeight = (bucketCounts[i] / maxCount) * chartHeight
      const y = chartBottom - barHeight

      // Bar gradient
      const gradient = ctx.createLinearGradient(x, y, x, chartBottom)
      gradient.addColorStop(0, '#6366f1')
      gradient.addColorStop(1, '#4338ca')
      ctx.fillStyle = gradient
      ctx.beginPath()
      ctx.roundRect(x, y, barWidth, barHeight, [3, 3, 0, 0])
      ctx.fill()

      // Bucket label
      ctx.fillStyle = '#9ca3af'
      ctx.font = '9px monospace'
      ctx.textAlign = 'center'
      ctx.fillText(BUCKETS[i].label, x + barWidth / 2, height - 4)
    }
  }, [latency])

  return (
    <div style={{
      background: 'var(--bg-card)',
      border: '1px solid var(--border)',
      borderRadius: '8px',
      padding: '12px',
    }}>
      <h3 style={{ fontSize: '12px', color: 'var(--text-secondary)', marginBottom: '12px' }}>
        LATENCY HISTOGRAM
      </h3>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
        <canvas
          ref={canvasRef}
          style={{ width: '100%', height: '140px', display: 'block' }}
        />
        <div style={{
          display: 'grid',
          gridTemplateColumns: '1fr 1fr',
          gap: '8px',
          alignContent: 'center',
        }}>
          <StatBox label="p50" value={latency ? formatNs(latency.p50) : '--'} />
          <StatBox label="p90" value={latency ? formatNs(latency.p90) : '--'} />
          <StatBox label="p95" value={latency ? formatNs(latency.p95) : '--'} />
          <StatBox label="p99" value={latency ? formatNs(latency.p99) : '--'} />
          <StatBox label="mean" value={latency ? formatNs(latency.mean) : '--'} />
          <StatBox label="min" value={latency ? formatNs(latency.min) : '--'} />
          <StatBox label="max" value={latency ? formatNs(latency.max) : '--'} highlight />
        </div>
      </div>
    </div>
  )
}

function StatBox({ label, value, highlight }) {
  return (
    <div style={{
      background: 'var(--bg-secondary)',
      borderRadius: '6px',
      padding: '8px',
      display: 'flex',
      flexDirection: 'column',
      gap: '2px',
    }}>
      <span style={{ fontSize: '10px', color: 'var(--text-secondary)', textTransform: 'uppercase' }}>
        {label}
      </span>
      <span style={{
        fontSize: '13px',
        fontWeight: 600,
        fontFamily: 'monospace',
        color: highlight ? 'var(--yellow)' : 'var(--text-primary)',
      }}>
        {value}
      </span>
    </div>
  )
}

function estimateBucketCounts(stats) {
  // Approximate bucket distribution from percentile stats
  // We place synthetic sample points based on known percentiles
  const points = [
    { pct: 0, val: stats.min },
    { pct: 50, val: stats.p50 },
    { pct: 90, val: stats.p90 },
    { pct: 95, val: stats.p95 },
    { pct: 99, val: stats.p99 },
    { pct: 100, val: stats.max },
  ]

  const count = stats.count || 1000
  const bucketCounts = new Array(BUCKETS.length).fill(0)

  // For each pair of consecutive percentile points, distribute samples into buckets
  for (let i = 0; i < points.length - 1; i++) {
    const pctRange = points[i + 1].pct - points[i].pct
    const samplesInRange = Math.round((pctRange / 100) * count)
    const valStart = points[i].val
    const valEnd = points[i + 1].val

    for (let s = 0; s < samplesInRange; s++) {
      // Linearly interpolate value
      const val = valStart + (valEnd - valStart) * (s / Math.max(samplesInRange - 1, 1))
      for (let b = 0; b < BUCKETS.length; b++) {
        if (val >= BUCKETS[b].min && val < BUCKETS[b].max) {
          bucketCounts[b]++
          break
        }
      }
    }
  }

  return bucketCounts
}
