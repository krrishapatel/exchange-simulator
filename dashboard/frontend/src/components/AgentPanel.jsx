import React from 'react'

const containerStyle = {
  background: 'var(--bg-card)',
  border: '1px solid var(--border)',
  borderRadius: '8px',
  padding: '12px',
}

export default function AgentPanel({ agents }) {
  if (!agents || agents.length === 0) {
    return (
      <div style={containerStyle}>
        <h3 style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>AGENTS</h3>
        <span style={{ color: 'var(--text-secondary)', fontSize: '12px' }}>Waiting...</span>
      </div>
    )
  }

  return (
    <div style={containerStyle}>
      <h3 style={{ fontSize: '12px', color: 'var(--text-secondary)', marginBottom: '12px' }}>
        AGENTS
      </h3>
      <div style={{ display: 'grid', gridTemplateColumns: `repeat(${Math.min(agents.length, 5)}, 1fr)`, gap: '12px' }}>
        {agents.map((agent) => {
          const pnlColor = agent.pnl > 0 ? 'var(--green)' : agent.pnl < 0 ? 'var(--red)' : 'var(--text-primary)'
          const invColor = Math.abs(agent.inventory) > 20 ? 'var(--yellow)' : 'var(--text-primary)'

          return (
            <div key={agent.name} style={{
              background: 'var(--bg-secondary)',
              borderRadius: '6px',
              padding: '10px',
              display: 'flex',
              flexDirection: 'column',
              gap: '6px',
            }}>
              <span style={{ fontSize: '12px', fontWeight: 600 }}>{agent.name}</span>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px' }}>
                <span style={{ color: 'var(--text-secondary)' }}>PnL</span>
                <span style={{ color: pnlColor }}>
                  {(agent.pnl / 10000).toFixed(2)}
                </span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px' }}>
                <span style={{ color: 'var(--text-secondary)' }}>Inventory</span>
                <span style={{ color: invColor }}>{agent.inventory}</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px' }}>
                <span style={{ color: 'var(--text-secondary)' }}>Fills</span>
                <span>{agent.fills}</span>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
