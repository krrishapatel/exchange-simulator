import React from 'react'

const cardStyle = {
  background: 'var(--bg-card)',
  border: '1px solid var(--border)',
  borderRadius: '8px',
  padding: '12px 16px',
  display: 'flex',
  flexDirection: 'column',
  gap: '4px',
}

export default function Stats({ book, step, fillCount }) {
  const mid = book?.mid ? (book.mid / 10000).toFixed(4) : '—'
  const spread = book?.spread ?? '—'
  const bidDepth = book?.bid_depth ?? 0
  const askDepth = book?.ask_depth ?? 0

  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: '12px' }}>
      <div style={cardStyle}>
        <span style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>MID PRICE</span>
        <span style={{ fontSize: '18px', fontWeight: 600 }}>{mid}</span>
      </div>
      <div style={cardStyle}>
        <span style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>SPREAD</span>
        <span style={{ fontSize: '18px', fontWeight: 600 }}>{spread}</span>
      </div>
      <div style={cardStyle}>
        <span style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>BID LEVELS</span>
        <span style={{ fontSize: '18px', fontWeight: 600 }}>{bidDepth}</span>
      </div>
      <div style={cardStyle}>
        <span style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>ASK LEVELS</span>
        <span style={{ fontSize: '18px', fontWeight: 600 }}>{askDepth}</span>
      </div>
      <div style={cardStyle}>
        <span style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>TOTAL FILLS</span>
        <span style={{ fontSize: '18px', fontWeight: 600 }}>{fillCount}</span>
      </div>
    </div>
  )
}
