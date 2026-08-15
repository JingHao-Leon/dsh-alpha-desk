const API = 'http://localhost:8321'

export interface Quote {
  symbol: string
  kind: string
  name?: string
  last_price?: number
  open_price?: number
  high_price?: number
  low_price?: number
  pre_close?: number
  limit_up?: number
  limit_down?: number
  volume?: number
  turnover?: number
  change_pct?: number
  turnover_rate?: number
  amplitude?: number
  pe_dynamic?: number | null
  pb?: number | null
  total_mv?: number
  stale?: boolean
}

export interface Bar {
  datetime: string
  open_price: number
  high_price: number
  low_price: number
  close_price: number
  volume: number
}

export async function fetchWatchlist(): Promise<Quote[]> {
  const r = await fetch(`${API}/api/watchlist`)
  if (!r.ok) throw new Error(`watchlist ${r.status}`)
  return r.json()
}

export async function fetchKline(symbol: string, period: string, count = 200): Promise<Bar[]> {
  const r = await fetch(`${API}/api/kline?symbol=${symbol}&period=${period}&count=${count}`)
  if (!r.ok) throw new Error(`kline ${r.status}`)
  return r.json()
}

export async function postChat(message: string, symbol?: string, symbolName?: string): Promise<string> {
  const r = await fetch(`${API}/api/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message, symbol, symbol_name: symbolName }),
  })
  if (!r.ok) {
    const detail = await r.json().catch(() => ({}))
    throw new Error(detail.detail || `chat ${r.status}`)
  }
  return (await r.json()).reply
}

export function openQuotesWS(onMessage: (quotes: Quote[]) => void): WebSocket {
  const ws = new WebSocket(`ws://localhost:8321/ws/quotes`)
  ws.onmessage = (ev) => onMessage(JSON.parse(ev.data))
  ws.onclose = () => setTimeout(() => openQuotesWS(onMessage), 3000) // auto-reconnect
  return ws
}
