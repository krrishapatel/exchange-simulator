import React from 'react'

const containerStyle = {
  background: 'var(--bg-card)',
  border: '1px solid var(--border)',
  borderRadius: '8px',
  padding: '12px',
  display: 'flex',
  flexDirection: 'column',
}

export default function OrderBook({ book }) {
  if (!book || !book.best_bid || !book.best_ask) {
    return (
      <div style={containerStyle}>
        <h3 style={{ fontSize: '12px', color: 'var(--text-secondary)', marginBottom: '8px' }}>
          ORDER BOOK
        </h3>
        <span style={{ color: 'var(--text-secondary)', fontSize: '13px' }}>Waiting for data...</span>
      </div>
    )
  }

  const mid = (book.best_bid + book.best_ask) / 2
  const tickSize = 1
  const levels = 8

  const asks = Array.from({ length: levels }, (_, i) => ({
    price: book.best_ask + (levels - 1 - i) * tickSize,
    side: 'ask',
  }))

  const bids = Array.from({ length: levels }, (_, i) => ({
    price: book.best_bid - i * tickSize,
    side: 'bid',
  }))

  return (
    <div style={containerStyle}>
      <h3 style={{ fontSize: '12px', color: 'var(--text-secondary)', marginBottom: '8px' }}>
        ORDER BOOK
      </h3>
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: '2px', fontSize: '12px' }}>
        {asks.map((level, i) => (
          <div key={`ask-${i}`} style={{
            display: 'flex',
            justifyContent: 'space-between',
            padding: '2px 4px',
            color: 'var(--red)',
            opacity: 0.5 + (i / levels) * 0.5,
          }}>
            <span>{(level.price / 10000).toFixed(4)}</span>
          </div>
        ))}

        <div style={{
          padding: '6px 4px',
          borderTop: '1px solid var(--border)',
          borderBottom: '1px solid var(--border)',
          margin: '4px 0',
          textAlign: 'center',
          fontSize: '13px',
          fontWeight: 600,
        }}>
          {(mid / 10000).toFixed(4)}
          <span style={{ fontSize: '10px', color: 'var(--text-secondary)', marginLeft: '8px' }}>
            spread: {book.spread}
          </span>
        </div>

        {bids.map((level, i) => (
          <div key={`bid-${i}`} style={{
            display: 'flex',
            justifyContent: 'space-between',
            padding: '2px 4px',
            color: 'var(--green)',
            opacity: 1 - (i / levels) * 0.5,
          }}>
            <span>{(level.price / 10000).toFixed(4)}</span>
          </div>
        ))}
      </div>
    </div>
  )
}
