import React, { useRef, useEffect } from 'react'

const containerStyle = {
  background: 'var(--bg-card)',
  border: '1px solid var(--border)',
  borderRadius: '8px',
  padding: '12px',
  display: 'flex',
  flexDirection: 'column',
}

export default function PriceChart({ data }) {
  const canvasRef = useRef(null)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas || data.length < 2) return

    const ctx = canvas.getContext('2d')
    const rect = canvas.getBoundingClientRect()
    canvas.width = rect.width * window.devicePixelRatio
    canvas.height = rect.height * window.devicePixelRatio
    ctx.scale(window.devicePixelRatio, window.devicePixelRatio)

    const w = rect.width
    const h = rect.height
    const padding = { top: 20, right: 10, bottom: 20, left: 50 }
    const plotW = w - padding.left - padding.right
    const plotH = h - padding.top - padding.bottom

    ctx.clearRect(0, 0, w, h)

    const values = data.map(d => d.value)
    const min = Math.min(...values)
    const max = Math.max(...values)
    const range = max - min || 1

    const toX = (i) => padding.left + (i / (data.length - 1)) * plotW
    const toY = (v) => padding.top + plotH - ((v - min) / range) * plotH

    // Grid lines
    ctx.strokeStyle = '#2d3748'
    ctx.lineWidth = 0.5
    for (let i = 0; i <= 4; i++) {
      const y = padding.top + (i / 4) * plotH
      ctx.beginPath()
      ctx.moveTo(padding.left, y)
      ctx.lineTo(w - padding.right, y)
      ctx.stroke()

      const label = (max - (i / 4) * range).toFixed(2)
      ctx.fillStyle = '#94a3b8'
      ctx.font = '10px monospace'
      ctx.textAlign = 'right'
      ctx.fillText(label, padding.left - 4, y + 3)
    }

    // Price line
    const lastValue = values[values.length - 1]
    const prevValue = values[values.length - 2]
    const isUp = lastValue >= prevValue

    ctx.beginPath()
    ctx.strokeStyle = isUp ? '#10b981' : '#ef4444'
    ctx.lineWidth = 1.5
    data.forEach((d, i) => {
      const x = toX(i)
      const y = toY(d.value)
      if (i === 0) ctx.moveTo(x, y)
      else ctx.lineTo(x, y)
    })
    ctx.stroke()

    // Fill gradient
    const gradient = ctx.createLinearGradient(0, padding.top, 0, padding.top + plotH)
    const color = isUp ? '16, 185, 129' : '239, 68, 68'
    gradient.addColorStop(0, `rgba(${color}, 0.1)`)
    gradient.addColorStop(1, `rgba(${color}, 0)`)

    ctx.lineTo(toX(data.length - 1), padding.top + plotH)
    ctx.lineTo(toX(0), padding.top + plotH)
    ctx.closePath()
    ctx.fillStyle = gradient
    ctx.fill()

    // Current price label
    ctx.fillStyle = isUp ? '#10b981' : '#ef4444'
    ctx.font = 'bold 12px monospace'
    ctx.textAlign = 'right'
    ctx.fillText(lastValue.toFixed(4), w - padding.right, padding.top - 6)
  }, [data])

  return (
    <div style={containerStyle}>
      <h3 style={{ fontSize: '12px', color: 'var(--text-secondary)', marginBottom: '8px' }}>
        MID PRICE
      </h3>
      <canvas
        ref={canvasRef}
        style={{ flex: 1, width: '100%', minHeight: '300px' }}
      />
    </div>
  )
}
