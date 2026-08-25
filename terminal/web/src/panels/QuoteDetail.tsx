import { useEffect, useState } from 'react'
import { fetchFundamentals, type Fundamentals, type Quote } from '../api'
import { Experts } from './Experts'

interface Props {
  quote?: Quote
  activity: string[]
}

function yi(v?: number) {
  return v === undefined ? '--' : (v / 1e8).toFixed(2) + '亿'
}

function pct(v?: number | null) {
  return v === null || v === undefined ? '--' : v.toFixed(2) + '%'
}

function num(v?: number | null) {
  return v === null || v === undefined ? '--' : String(v)
}

function FundamentalsBlock({ quote }: { quote?: Quote }) {
  const [data, setData] = useState<Fundamentals | null>(null)
  const [state, setState] = useState<'idle' | 'loading' | 'error' | 'na'>('idle')

  useEffect(() => {
    if (!quote?.symbol) return
    setState('loading')
    setData(null)
    fetchFundamentals(quote.symbol, quote.kind)
      .then((d) => { setData(d); setState('idle') })
      .catch((e) => setState(String(e).includes('404') ? 'na' : 'error'))
  }, [quote?.symbol, quote?.kind])

  if (!quote || state === 'na') return null
  const p = data?.profitability
  const g = data?.growth
  const rows: [string, string][] = data ? [
    ['ROE', pct(p?.roe)],
    ['毛利率', pct(p?.grossMargin)],
    ['净利率', pct(p?.netMargin)],
    ['EPS', num(p?.eps)],
    ['每股净资产', num(p?.bps)],
    ['营收同比', pct(g?.revenueYoY)],
    ['净利同比', pct(g?.netProfitYoY)],
    ['实控人', data.profile.controllerType || '--'],
  ] : []

  return (
    <>
      <div className="panel-title" style={{ marginTop: 12 }}>
        基本面 <span className="dim">iFinD{data?.reportPeriod ? ` · ${data.reportPeriod}` : ''}</span>
      </div>
      {state === 'loading' && <div className="dim" style={{ padding: 8, fontSize: 12 }}>iFinD 数据加载中…</div>}
      {state === 'error' && <div className="dim" style={{ padding: 8, fontSize: 12 }}>基本面数据暂不可用</div>}
      {data && (
        <>
          <div className="quote-grid">
            {rows.map(([k, v]) => (
              <div key={k} className="quote-cell"><span>{k}</span><b>{v}</b></div>
            ))}
          </div>
          {data.profile.mainBusiness && (
            <div className="fund-biz">主营:{data.profile.mainBusiness}</div>
          )}
        </>
      )}
    </>
  )
}

export function QuoteDetail({ quote, activity }: Props) {
  const [tab, setTab] = useState<'quote' | 'experts'>('quote')
  const q = quote
  const pctChange = q?.change_pct ?? 0
  const cls = pctChange > 0 ? 'up' : pctChange < 0 ? 'down' : 'flat'
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
      <div className="detail-tabs">
        <button className={tab === 'quote' ? 'on' : ''} onClick={() => setTab('quote')}>报价</button>
        <button className={tab === 'experts' ? 'on' : ''} onClick={() => setTab('experts')}>专家团</button>
      </div>
      <div style={{ display: tab === 'quote' ? 'block' : 'none' }}>
        <div className="quote-head">
          <div className="quote-name">{q?.name ?? '--'} <i>{q?.symbol}</i></div>
          <div className={`quote-price ${cls}`}>{q?.last_price?.toFixed(2) ?? '--'}</div>
          <div className={`quote-pct ${cls}`}>{pctChange > 0 ? '+' : ''}{pctChange.toFixed(2)}%</div>
        </div>
        <div className="quote-grid">
          {rows.map(([k, v]) => (
            <div key={k} className="quote-cell"><span>{k}</span><b>{v}</b></div>
          ))}
        </div>
        <FundamentalsBlock quote={quote} />
        <div className="panel-title" style={{ marginTop: 12 }}>agent 动态</div>
        <div className="activity">
          {activity.length === 0 && <div className="dim" style={{ padding: 8 }}>暂无动作</div>}
          {activity.map((a, i) => <div key={i} className="activity-item">{a}</div>)}
        </div>
      </div>
      <div style={{ display: tab === 'experts' ? 'block' : 'none' }}>
        <Experts />
      </div>
    </aside>
  )
}
