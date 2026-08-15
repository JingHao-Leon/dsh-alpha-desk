import { useEffect, useRef, useState } from 'react'
import { postChat, type Trace } from '../api'

interface Msg {
  role: 'user' | 'agent' | 'error'
  text: string
  time: string
  trace?: Trace | null
}

interface Props {
  symbol: string
  symbolName?: string
  onActivity: (text: string) => void
}

const now = () => new Date().toLocaleTimeString('zh-CN', { hour12: false })

function fmtTokens(n?: number) {
  if (n === undefined) return '--'
  return n >= 1000 ? `${(n / 1000).toFixed(1)}k` : String(n)
}

function TraceView({ trace }: { trace: Trace }) {
  const [open, setOpen] = useState(false)
  const t = trace.totals
  const secs = (trace.durationMs / 1000).toFixed(1)
  return (
    <div className="trace">
      <button className="trace-summary" onClick={() => setOpen(!open)}>
        <span>{open ? '▾' : '▸'} 运行轨迹</span>
        <span className="dim">
          {t.steps} 步 · {t.toolCalls} 次工具调用 · 输入 {fmtTokens(t.inputTokens)}
          {t.cacheReadTokens ? `(+${fmtTokens(t.cacheReadTokens)} 缓存)` : ''}
          {' · 输出 '}{fmtTokens(t.outputTokens)}
          {t.reasoningTokens ? ` · 思考 ${fmtTokens(t.reasoningTokens)}` : ''}
          {' · '}{secs}s
        </span>
      </button>
      {open && (
        <div className="trace-steps">
          {trace.steps.map((s) => (
            <div key={s.step} className="trace-step">
              <div className="trace-step-head">
                <span className="trace-step-no">step {s.step}</span>
                {s.usage && (
                  <span className="dim">
                    in {fmtTokens(s.usage.inputTokens)} · out {fmtTokens(s.usage.outputTokens)}
                    {s.usage.reasoningTokens ? ` · 思考 ${fmtTokens(s.usage.reasoningTokens)}` : ''}
                  </span>
                )}
              </div>
              {s.reasoning && <div className="trace-reasoning">💭 {s.reasoning}</div>}
              {s.tools.map((tool) => (
                <div key={tool.callId} className="trace-tool">
                  <div className="trace-tool-call">🔧 <b>{tool.name}</b> <code>{tool.summary}</code></div>
                  {tool.result && (
                    <details className="trace-tool-result">
                      <summary>结果</summary>
                      <div>{tool.result}</div>
                    </details>
                  )}
                </div>
              ))}
            </div>
          ))}
          {trace.model && <div className="trace-foot dim">model: {trace.model}</div>}
        </div>
      )}
    </div>
  )
}

export function Chat({ symbol, symbolName, onActivity }: Props) {
  const [msgs, setMsgs] = useState<Msg[]>([{
    role: 'agent',
    text: '这里是 alpha-desk 量化终端。选中左侧标的后直接提问,例如「分析这只票今天的走势」。所有回复都经过 risk-gate 风控插件,仅供学习研究。',
    time: now(),
  }])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const listRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight })
  }, [msgs, busy])

  async function send() {
    const text = input.trim()
    if (!text || busy) return
    setInput('')
    setMsgs((m) => [...m, { role: 'user', text, time: now() }])
    onActivity(`提问:${text.slice(0, 24)}${text.length > 24 ? '…' : ''}`)
    setBusy(true)
    try {
      const resp = await postChat(text, symbol, symbolName)
      setMsgs((m) => [...m, { role: 'agent', text: resp.reply, time: now(), trace: resp.trace }])
      const t = resp.trace?.totals
      onActivity(t
        ? `回复完成 · ${t.steps} 步/${t.toolCalls} 次工具 · ${fmtTokens(t.inputTokens)}+${fmtTokens(t.outputTokens)} tokens`
        : 'agent 回复完成')
    } catch (e) {
      setMsgs((m) => [...m, { role: 'error', text: String(e), time: now() }])
      onActivity('agent 调用失败')
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="chat">
      <div className="panel-title">
        对话 <span className="dim">DeepSeek V4 Pro · dsh headless · risk-gate 已挂载</span>
      </div>
      <div className="chat-list" ref={listRef}>
        {msgs.map((m, i) => (
          <div key={i} className={`msg ${m.role}`}>
            <div className="msg-meta">{m.role === 'user' ? '你' : m.role === 'agent' ? 'alpha-desk' : '错误'} · {m.time}</div>
            <div className="msg-body">
              {m.text}
              {m.trace && <TraceView trace={m.trace} />}
            </div>
          </div>
        ))}
        {busy && <div className="msg agent"><div className="msg-meta">alpha-desk</div><div className="msg-body thinking">分析中,通常 30-120 秒…</div></div>}
      </div>
      <div className="chat-input">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && send()}
          placeholder={`就 ${symbolName ?? symbol} 提问…`}
          disabled={busy}
        />
        <button onClick={send} disabled={busy || !input.trim()}>发送</button>
      </div>
    </section>
  )
}
