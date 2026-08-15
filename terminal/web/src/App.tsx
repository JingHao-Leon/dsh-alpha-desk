import { useEffect, useMemo, useState } from 'react'
import './App.css'
import { fetchWatchlist, openQuotesWS, type Quote } from './api'
import { Watchlist } from './panels/Watchlist'
import { Chat } from './panels/Chat'
import { Kline } from './panels/Kline'
import { QuoteDetail } from './panels/QuoteDetail'

export default function App() {
  const [quotes, setQuotes] = useState<Quote[]>([])
  const [selected, setSelected] = useState('600519')
  const [activity, setActivity] = useState<string[]>([])

  useEffect(() => {
    fetchWatchlist().then(setQuotes).catch(console.error)
    const ws = openQuotesWS(setQuotes)
    return () => ws.close()
  }, [])

  const current = useMemo(
    () => quotes.find((q) => q.symbol === selected),
    [quotes, selected],
  )

  const log = (text: string) =>
    setActivity((a) => [`${new Date().toLocaleTimeString('zh-CN', { hour12: false })} ${text}`, ...a].slice(0, 30))

  return (
    <div className="terminal">
      <header className="topbar">
        <span className="logo">alpha-desk <b>TERMINAL</b></span>
        <span className="tag">DeepSeek Harness × vnpy · 只读研究终端</span>
        <span className="clock">{new Date().toLocaleString('zh-CN', { hour12: false })}</span>
      </header>
      <div className="layout">
        <Watchlist quotes={quotes} selected={selected} onSelect={(q) => setSelected(q.symbol)} />
        <main className="center">
          <Chat symbol={selected} symbolName={current?.name} onActivity={log} />
          <Kline symbol={selected} name={current?.name} />
        </main>
        <QuoteDetail quote={current} activity={activity} />
      </div>
      <footer className="statusbar">
        数据:腾讯行情(免费,分钟级延迟) · agent:dsh headless + alpha-desk skill + risk-gate · 本终端仅供学习研究,不构成投资建议
      </footer>
    </div>
  )
}
