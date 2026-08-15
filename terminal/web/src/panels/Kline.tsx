import { useEffect, useRef, useState } from 'react'
import { init, dispose, type Chart, type KLineData } from 'klinecharts'
import { fetchKline } from '../api'

const PERIODS = [
  { key: 'daily', label: '日K' },
  { key: '60', label: '60分' },
  { key: '15', label: '15分' },
  { key: '5', label: '5分' },
]

interface Props {
  symbol: string
  name?: string
}

export function Kline({ symbol, name }: Props) {
  const ref = useRef<HTMLDivElement>(null)
  const chart = useRef<Chart | null>(null)
  const [period, setPeriod] = useState('daily')
  const [err, setErr] = useState('')

  useEffect(() => {
    if (!ref.current) return
    chart.current = init(ref.current, {
      styles: {
        grid: {
          horizontal: { color: '#1c2430' },
          vertical: { color: '#1c2430' },
        },
        candle: {
          bar: {
            upColor: '#e54545', downColor: '#2ebd85', noChangeColor: '#888888',
            upBorderColor: '#e54545', downBorderColor: '#2ebd85', noChangeBorderColor: '#888888',
            upWickColor: '#e54545', downWickColor: '#2ebd85', noChangeWickColor: '#888888',
          },
          priceMark: {
            high: { color: '#8b94a3' },
            low: { color: '#8b94a3' },
            last: {
              upColor: '#e54545', downColor: '#2ebd85', noChangeColor: '#888',
            },
          },
        },
        indicator: {
          lastValueMark: { show: false },
        },
        xAxis: { axisLine: { color: '#2a3546' }, tickText: { color: '#8b94a3' } },
        yAxis: { axisLine: { color: '#2a3546' }, tickText: { color: '#8b94a3' } },
        crosshair: {
          horizontal: { line: { color: '#3b82f6' }, text: { backgroundColor: '#3b82f6' } },
          vertical: { line: { color: '#3b82f6' }, text: { backgroundColor: '#3b82f6' } },
        },
      },
    })
    chart.current?.createIndicator('MA', false, { id: 'candle_pane' })
    chart.current?.createIndicator('VOL', false, { height: 80 })
    const instance = chart.current
    return () => { dispose(instance!) ; chart.current = null }
  }, [])

  useEffect(() => {
    let cancelled = false
    setErr('')
    fetchKline(symbol, period, 200)
      .then((bars) => {
        if (cancelled || !chart.current) return
        const data: KLineData[] = bars.map((b) => ({
          timestamp: new Date(b.datetime).getTime(),
          open: b.open_price,
          high: b.high_price,
          low: b.low_price,
          close: b.close_price,
          volume: b.volume,
        }))
        chart.current!.applyNewData(data)
      })
      .catch((e) => !cancelled && setErr(String(e)))
    return () => { cancelled = true }
  }, [symbol, period])

  return (
    <section className="kline">
      <div className="panel-title kline-title">
        <span>{name ?? symbol} <i className="dim">{symbol}</i></span>
        <span className="period-tabs">
          {PERIODS.map((p) => (
            <button key={p.key} className={period === p.key ? 'on' : ''} onClick={() => setPeriod(p.key)}>{p.label}</button>
          ))}
        </span>
      </div>
      {err && <div className="kline-err">{err}</div>}
      <div className="kline-body" ref={ref} />
    </section>
  )
}
