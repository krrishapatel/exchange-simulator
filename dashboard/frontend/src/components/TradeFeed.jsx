import React from 'react'

const containerStyle = {
  background: 'var(--bg-card)',
  border: '1px solid var(--border)',
  borderRadius: '8px',
  padding: '12px',
  display: 'flex',
  flexDirection: 'column',
  overflow: 'hidden',
}

export default function TradeFeed({ fills }) {
  return (
    <div style={containerStyle}>
      <h3 style={{ fontSize: '12px', color: 'var(--text-secondary)', marginBottom: '8px' }}>
        TRADE FEED
      </h3>
      <div style={{ flex: 1, overflow: 'auto', display: 'flex', flexDirection: 'column', gap: '2px' }}>
        {fills.length === 0 ? (
          <span style={{ color: 'var(--text-secondary)', fontSize: '12px' }}>No trades yet</span>
        ) : (
          fills.slice(0, 30).map((fill, i) => (
            <div key={i} style={{
              display: 'flex',
              justifyContent: 'space-between',
              fontSize: '11px',
              padding: '2px 4px',
              borderRadius: '3px',
              background: i === 0 ? 'rgba(255,255,255,0.03)' : 'transparent',
            }}>
              <span style={{ color: fill.side === 'Buy' ? 'var(--green)' : 'var(--red)' }}>
                {fill.side === 'Buy' ? 'BUY' : 'SELL'}
              </span>
              <span>{(fill.price / 10000).toFixed(4)}</span>
              <span style={{ color: 'var(--text-secondary)' }}>{fill.quantity}</span>
            </div>
          ))
        )}
      </div>
    </div>
  )
}
