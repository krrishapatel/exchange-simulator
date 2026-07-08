# Exchange Simulator Dashboard

Live visualization of the exchange simulation showing order book, price chart, trade feed, and agent performance.

## Architecture

```
Browser (React + Canvas)  ←—WebSocket—→  Python server  ←→  C++ Engine
```

## Running

### 1. Start the WebSocket server

```bash
cd exchange-simulator
pip install websockets
PYTHONPATH=build/bindings:. python3 dashboard/server/app.py
```

### 2. Start the frontend

```bash
cd dashboard/frontend
npm install
npm run dev
```

Open http://localhost:3000

## Features

- **Order Book** — Live best bid/ask with 8-level depth
- **Price Chart** — Canvas-rendered mid-price with gradient fill
- **Trade Feed** — Scrolling list of recent executions
- **Agent Panel** — Real-time PnL, inventory, and fill counts per agent
- **Stats Bar** — Mid price, spread, book depth, total fills
