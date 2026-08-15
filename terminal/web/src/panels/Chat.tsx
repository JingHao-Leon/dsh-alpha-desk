import { useEffect, useRef, useState } from 'react'
import { postChat } from '../api'

interface Msg {
  role: 'user' | 'agent' | 'error'
  text: string
  time: string
}

interface Props {
  symbol: string
  symbolName?: string
  onActivity: (text: string) => void
}

const now = () => new Date().toLocaleTimeString('zh-CN', { hour12: false })

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
      const reply = await postChat(text, symbol, symbolName)
      setMsgs((m) => [...m, { role: 'agent', text: reply, time: now() }])
      onActivity('agent 回复完成')
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
            <div className="msg-body">{m.text}</div>
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
