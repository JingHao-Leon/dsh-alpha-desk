import { useState } from 'react'
import { postExperts, type ExpertsResponse } from '../api'

function stance(value: number): { text: string; cls: string } {
  if (value >= 0.2) return { text: '看多', cls: 'up' }
  if (value <= -0.2) return { text: '看空', cls: 'down' }
  return { text: '中性', cls: 'flat' }
}

export function Experts() {
  const [tickers, setTickers] = useState('AAPL,MSFT,NVDA')
  const [data, setData] = useState<ExpertsResponse | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  async function run() {
    if (busy || !tickers.trim()) return
    setBusy(true)
    setError('')
    try {
      setData(await postExperts(tickers.trim()))
    } catch (e) {
      setError(String(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="experts">
      <div className="experts-bar">
        <input
          value={tickers}
          onChange={(e) => setTickers(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && run()}
          placeholder="AAPL,MSFT,NVDA"
          disabled={busy}
        />
        <button onClick={run} disabled={busy || !tickers.trim()}>
          {busy ? '讨论中…' : '召开专家团'}
        </button>
      </div>
      {busy && <div className="dim experts-hint">aihf 多模型推理中,真实运行约 1-3 分钟…</div>}
      {error && <div className="experts-err">{error}</div>}
      {data?.demo && <div className="experts-demo">示例数据 · {data.note}</div>}
      {data && !data.demo && <div className="dim experts-hint">asOf {data.asOf} · 真实 aihf 信号,已存 records/</div>}
      {data?.experts.map((ex) => {
        const avg = ex.signals.length
          ? ex.signals.reduce((a, s) => a + (s.value || 0), 0) / ex.signals.length
          : 0
        const st = stance(avg)
        return (
          <div key={ex.model} className="expert-card">
            <div className="expert-head">
              <b>{ex.label}</b>
              <span className={st.cls}>{st.text} {avg >= 0 ? '+' : ''}{avg.toFixed(2)}</span>
            </div>
            <div className="expert-meter">
              <div className={`expert-meter-fill ${st.cls}-bg`} style={{ width: `${Math.min(Math.abs(avg) * 100, 100)}%` }} />
            </div>
            {ex.signals.map((s, i) => {
              const ss = stance(s.value || 0)
              return (
                <div key={i} className="expert-signal">
                  <div className="expert-signal-head">
                    <span className="expert-ticker">{s.ticker}</span>
                    <span className={ss.cls}>{ss.text} {s.value >= 0 ? '+' : ''}{(s.value || 0).toFixed(2)}</span>
                  </div>
                  <div className="expert-reasoning">{s.reasoning}</div>
                </div>
              )
            })}
          </div>
        )
      })}
      {data?.positions && data.positions.length > 0 && (
        <div className="expert-card">
          <div className="expert-head"><b>组合经理结论</b></div>
          {data.positions.map((p, i) => (
            <div key={i} className="expert-signal-head">
              <span className="expert-ticker">{p.ticker}</span>
              <span className="dim">{p.action ?? '--'} {p.weight !== undefined ? `${(p.weight * 100).toFixed(0)}%` : ''}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
