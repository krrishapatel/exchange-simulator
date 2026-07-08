import React, { useState, useEffect, useRef, useCallback } from 'react'
import OrderBook from './components/OrderBook'
import TradeFeed from './components/TradeFeed'
import AgentPanel from './components/AgentPanel'
import PriceChart from './components/PriceChart'
import Stats from './components/Stats'

export default function App() {
  const [connected, setConnected] = useState(false)
  const [book, setBook] = useState(null)
  const [agents, setAgents] = useState([])
  const [fills, setFills] = useState([])
  const [priceHistory, setPriceHistory] = useState([])
  const [step, setStep] = useState(0)
  const wsRef = useRef(null)

  const connect = useCallback(() => {
    const ws = new WebSocket('ws://localhost:8765')
    wsRef.current = ws

    ws.onopen = () => setConnected(true)
    ws.onclose = () => {
      setConnected(false)
      setTimeout(connect, 2000)
    }
    ws.onerror = () => ws.close()

    ws.onmessage = (event) => {
      const data = JSON.parse(event.data)
      if (data.type === 'tick') {
        setBook(data.book)
        setAgents(data.agents)
        setStep(data.step)

        if (data.fills.length > 0) {
          setFills(prev => [...data.fills, ...prev].slice(0, 100))
        }

        if (data.book.mid) {
          setPriceHistory(prev => {
            const next = [...prev, { time: data.step, value: data.book.mid / 10000 }]
            return next.slice(-500)
          })
        }
      }
    }
  }, [])

  useEffect(() => {
    connect()
    return () => wsRef.current?.close()
  }, [connect])

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
      <header style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        padding: '8px 16px',
        background: 'var(--bg-card)',
        borderRadius: '8px',
        border: '1px solid var(--border)',
      }}>
        <h1 style={{ fontSize: '16px', fontWeight: 600 }}>Exchange Simulator</h1>
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <span style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
            Step {step.toLocaleString()}
          </span>
          <span style={{
            width: '8px',
            height: '8px',
            borderRadius: '50%',
            background: connected ? 'var(--green)' : 'var(--red)',
          }} />
        </div>
      </header>

      <Stats book={book} step={step} fillCount={fills.length} />

      <div style={{
        display: 'grid',
        gridTemplateColumns: '1fr 2fr 1fr',
        gap: '16px',
        minHeight: '400px',
      }}>
        <OrderBook book={book} />
        <PriceChart data={priceHistory} />
        <TradeFeed fills={fills} />
      </div>

      <AgentPanel agents={agents} />
    </div>
  )
}
