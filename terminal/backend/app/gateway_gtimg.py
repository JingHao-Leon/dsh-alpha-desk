"""Tencent (gtimg) market-data gateway.

Fetches free A-share quotes and klines from Tencent's public endpoints
(qt.gtimg.cn / web.ifzq.gtimg.cn) and returns vnpy-native objects
(BarData / TickData), so the rest of the terminal only ever sees vnpy data
structures. The class deliberately mirrors the query surface of a vnpy
BaseGateway: swapping in a real CTP/SimNow gateway later is a drop-in
replacement.

Why not akshare's eastmoney endpoints: they are intermittently unreachable
from some networks, while qt.gtimg.cn has proven stable. One batched request
quotes the whole watchlist (stocks and indices mixed).
"""
from __future__ import annotations

import datetime as dt
from dataclasses import asdict

import requests

try:
    from vnpy.trader.object import BarData, TickData
    from vnpy.trader.constant import Exchange, Interval
except ImportError:  # pragma: no cover - fallback when vnpy is not installed
    from .vnpy_compat import BarData, TickData, Exchange, Interval

GATEWAY_NAME = "GTIMG"
QUOTE_URL = "https://qt.gtimg.cn/q={symbols}"
KLINE_URL = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
MKLINE_URL = "https://ifzq.gtimg.cn/appstock/app/kline/mkline"

# v_<code> quote field indices (gbk, '~'-separated)
F_NAME, F_CODE, F_LAST, F_PRE_CLOSE, F_OPEN, F_VOLUME = 1, 2, 3, 4, 5, 6
F_TIME, F_CHANGE, F_CHANGE_PCT, F_HIGH, F_LOW = 30, 31, 32, 33, 34
F_TURNOVER_WAN, F_TURNOVER_RATE, F_PE, F_AMPLITUDE = 37, 38, 39, 43
F_FLOAT_MV, F_TOTAL_MV, F_PB = 44, 45, 46
F_LIMIT_UP, F_LIMIT_DOWN = 47, 48


def market_prefix(symbol: str, kind: str = "stock") -> str:
    # stocks: 6xx/9xx → SH, else SZ; indices: 000xxx → SH, 399xxx → SZ
    if kind == "index":
        return "sh" if symbol.startswith("0") else "sz"
    return "sh" if symbol.startswith(("6", "9")) else "sz"


def to_exchange(symbol: str, kind: str = "stock") -> "Exchange":
    return Exchange.SSE if market_prefix(symbol, kind) == "sh" else Exchange.SZSE


def _f(fields: list[str], idx: int, default: float = 0.0) -> float:
    try:
        v = fields[idx]
        return float(v) if v else default
    except (IndexError, TypeError, ValueError):
        return default


class TencentGateway:
    """Read-only quote/bar source. Interface follows vnpy gateway conventions."""

    def __init__(self, timeout: float = 8.0) -> None:
        self.session = requests.Session()
        self.session.trust_env = False  # macOS system proxy breaks this channel
        self.timeout = timeout

    # -- snapshots -----------------------------------------------------------
    def query_quotes(self, items: list[tuple[str, str]]) -> list[TickData]:
        """Batch-quote (symbol, kind) pairs — stocks and indices mixed in one request."""
        if not items:
            return []
        coded = ",".join(market_prefix(s, k) + s for s, k in items)
        kinds = {s: k for s, k in items}
        resp = self.session.get(QUOTE_URL.format(symbols=coded), timeout=self.timeout)
        resp.raise_for_status()
        resp.encoding = "gbk"

        ticks: list[TickData] = []
        for line in resp.text.split(";"):
            line = line.strip()
            if not line.startswith("v_") or '="' not in line:
                continue
            fields = line.split('="', 1)[1].rstrip('"').split("~")
            symbol = fields[F_CODE] if len(fields) > F_CODE else ""
            if not symbol:
                continue
            try:
                when = dt.datetime.strptime(fields[F_TIME], "%Y%m%d%H%M%S")
            except (IndexError, ValueError):
                when = dt.datetime.now()
            tick = TickData(
                symbol=symbol,
                exchange=to_exchange(symbol, kinds.get(symbol, "stock")),
                datetime=when,
                name=fields[F_NAME],
                volume=_f(fields, F_VOLUME) * 100,          # 手 → 股
                turnover=_f(fields, F_TURNOVER_WAN) * 1e4,  # 万 → 元
                last_price=_f(fields, F_LAST),
                open_price=_f(fields, F_OPEN),
                high_price=_f(fields, F_HIGH),
                low_price=_f(fields, F_LOW),
                pre_close=_f(fields, F_PRE_CLOSE),
                limit_up=_f(fields, F_LIMIT_UP),
                limit_down=_f(fields, F_LIMIT_DOWN),
                gateway_name=GATEWAY_NAME,
            )
            tick.extra = {
                "change_pct": _f(fields, F_CHANGE_PCT),
                "turnover_rate": _f(fields, F_TURNOVER_RATE),
                "amplitude": _f(fields, F_AMPLITUDE),
                "pe_dynamic": _f(fields, F_PE) or None,
                "pb": _f(fields, F_PB) or None,
                "float_mv": _f(fields, F_FLOAT_MV) * 1e8,  # 亿 → 元
                "total_mv": _f(fields, F_TOTAL_MV) * 1e8,
            }
            ticks.append(tick)
        return ticks

    # -- history -------------------------------------------------------------
    def query_bars(self, symbol: str, period: str = "daily", count: int = 200,
                   kind: str = "stock") -> list[BarData]:
        """period: daily | 60 | 30 | 15 | 5. Returns oldest→newest BarData list."""
        code = market_prefix(symbol, kind) + symbol
        if period == "daily":
            fq = "" if kind == "index" else "qfq"
            data = self._get(KLINE_URL, {"param": f"{code},day,,,{count},{fq}"})
            payload = data[code]
            rows = payload.get("qfqday") or payload.get("day") or []
            interval = Interval.DAILY
        else:
            data = self._get(MKLINE_URL, {"param": f"{code},m{period},,{count}"})
            rows = data[code].get(f"m{period}") or []
            interval = Interval.MINUTE

        bars: list[BarData] = []
        for row in rows[-count:]:
            # row: [date|datetime, open, close, high, low, volume]
            raw = str(row[0])
            if " " in raw or "T" in raw:
                when = dt.datetime.fromisoformat(raw)
            elif raw.isdigit() and len(raw) == 12:      # YYYYMMDDHHMM
                when = dt.datetime.strptime(raw, "%Y%m%d%H%M")
            else:
                when = dt.datetime.combine(dt.date.fromisoformat(raw), dt.time(15, 0))
            bars.append(
                BarData(
                    symbol=symbol,
                    exchange=to_exchange(symbol, kind),
                    datetime=when,
                    interval=interval,
                    volume=float(row[5]) * (100 if period == "daily" and kind != "index" else 1),
                    turnover=0.0,
                    open_price=float(row[1]),
                    close_price=float(row[2]),
                    high_price=float(row[3]),
                    low_price=float(row[4]),
                    gateway_name=GATEWAY_NAME,
                )
            )
        return bars

    def _get(self, url: str, params: dict) -> dict:
        resp = self.session.get(url, params=params, timeout=self.timeout)
        resp.raise_for_status()
        payload = resp.json()
        if payload.get("code") != 0:
            raise RuntimeError(f"gtimg error: {payload.get('msg')}")
        return payload["data"]


def bar_to_dict(bar: BarData) -> dict:
    d = asdict(bar)
    d["datetime"] = bar.datetime.isoformat()
    d["exchange"] = bar.exchange.value
    d["interval"] = bar.interval.value if bar.interval else None
    return d


def tick_to_dict(tick: TickData) -> dict:
    d = {
        "symbol": tick.symbol,
        "exchange": tick.exchange.value,
        "name": tick.name,
        "datetime": tick.datetime.isoformat(),
        "last_price": tick.last_price,
        "open_price": tick.open_price,
        "high_price": tick.high_price,
        "low_price": tick.low_price,
        "pre_close": tick.pre_close,
        "limit_up": tick.limit_up,
        "limit_down": tick.limit_down,
        "volume": tick.volume,
        "turnover": tick.turnover,
        "gateway_name": tick.gateway_name,
    }
    if tick.extra:
        d.update(tick.extra)
    return d
