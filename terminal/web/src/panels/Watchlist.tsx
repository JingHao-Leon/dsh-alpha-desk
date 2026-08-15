import type { Quote } from '../api'

interface Props {
  quotes: Quote[]
  selected: string
  onSelect: (q: Quote) => void
}

export function Watchlist({ quotes, selected, onSelect }: Props) {
  return (
    <aside className="watchlist">
      <div className="panel-title">自选行情</div>
      <div className="wl-head">
        <span>名称</span><span>最新</span><span>涨跌%</span>
      </div>
      {quotes.map((q) => {
        const pct = q.change_pct ?? 0
        const cls = pct > 0 ? 'up' : pct < 0 ? 'down' : 'flat'
        return (
          <button
            key={q.symbol}
            className={`wl-row ${q.symbol === selected ? 'active' : ''}`}
            onClick={() => onSelect(q)}
          >
            <span className="wl-name">
              <b>{q.name ?? q.symbol}</b>
              <i>{q.symbol}</i>
            </span>
            <span className={`wl-price ${cls}`}>{q.last_price?.toFixed(2) ?? '--'}</span>
            <span className={`wl-pct ${cls}`}>{pct > 0 ? '+' : ''}{pct.toFixed(2)}</span>
          </button>
        )
      })}
      <div className="wl-foot">数据源 GTIMG · 15s 刷新</div>
    </aside>
  )
}
