import type { Quote } from '../api'

interface Props {
  quote?: Quote
  activity: string[]
}

function yi(v?: number) {
  return v === undefined ? '--' : (v / 1e8).toFixed(2) + '亿'
}

export function QuoteDetail({ quote, activity }: Props) {
  const q = quote
  const pct = q?.change_pct ?? 0
  const cls = pct > 0 ? 'up' : pct < 0 ? 'down' : 'flat'
  const rows: [string, string, string?][] = q ? [
    ['今开', q.open_price?.toFixed(2) ?? '--'],
    ['昨收', q.pre_close?.toFixed(2) ?? '--'],
    ['最高', q.high_price?.toFixed(2) ?? '--'],
    ['最低', q.low_price?.toFixed(2) ?? '--'],
    ['涨停', q.limit_up ? q.limit_up.toFixed(2) : '--'],
    ['跌停', q.limit_down ? q.limit_down.toFixed(2) : '--'],
    ['换手率', q.turnover_rate !== undefined ? q.turnover_rate + '%' : '--'],
    ['振幅', q.amplitude !== undefined ? q.amplitude + '%' : '--'],
    ['市盈率', q.pe_dynamic?.toFixed(2) ?? '--'],
    ['市净率', q.pb?.toFixed(2) ?? '--'],
    ['总市值', yi(q.total_mv)],
    ['成交额', yi(q.turnover)],
  ] : []

  return (
    <aside className="detail">
      <div className="quote-head">
        <div className="quote-name">{q?.name ?? '--'} <i>{q?.symbol}</i></div>
        <div className={`quote-price ${cls}`}>{q?.last_price?.toFixed(2) ?? '--'}</div>
        <div className={`quote-pct ${cls}`}>{pct > 0 ? '+' : ''}{pct.toFixed(2)}%</div>
      </div>
      <div className="quote-grid">
        {rows.map(([k, v]) => (
          <div key={k} className="quote-cell"><span>{k}</span><b>{v}</b></div>
        ))}
      </div>
      <div className="panel-title" style={{ marginTop: 12 }}>agent 动态</div>
      <div className="activity">
        {activity.length === 0 && <div className="dim" style={{ padding: 8 }}>暂无动作</div>}
        {activity.map((a, i) => <div key={i} className="activity-item">{a}</div>)}
      </div>
    </aside>
  )
}
