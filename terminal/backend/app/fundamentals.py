"""iFinD fundamentals for the terminal UI.

Direct agent-gw calls (same credential chain as plugins/ifind/ifind_tool.py,
imported from agent_bridge), normalized into a compact JSON for the quote
panel. Results are cached on disk for CACHE_TTL seconds — fundamentals change
quarterly and the free agent-gw quota is monthly, so repeat views must not
re-hit the API.
"""
from __future__ import annotations

import csv
import io
import json
import time
from pathlib import Path

from .agent_bridge import _load_ifind_env

CACHE_DIR = Path(__file__).resolve().parent / "fundamentals_cache"
CACHE_TTL_SECONDS = 7 * 86400
TIMEOUT = 60.0


def _ticker(symbol: str, kind: str) -> str | None:
    """6 位代码 -> iFinD ticker;指数等非股票返回 None。"""
    if kind != "stock" or not symbol.isdigit():
        return None
    if symbol.startswith(("60", "68", "90")):
        return f"{symbol}.SH"
    if symbol.startswith(("00", "30", "20")):
        return f"{symbol}.SZ"
    if symbol.startswith(("43", "83", "87", "92")):
        return f"{symbol}.BJ"
    return f"{symbol}.SH"


def _candidate_periods() -> list[str]:
    """最近的几个报告期(新到旧),用于数据未披露时逐级回退。"""
    now = time.localtime()
    y, m = now.tm_year, now.tm_mon
    periods = []
    if m >= 8:
        periods.append(f"{y}0630")
    if m >= 5:
        periods.append(f"{y}0331")
    periods.append(f"{y - 1}1231")
    periods.append(f"{y - 1}0930")
    periods.append(f"{y - 1}0630")
    return periods


def _client():
    from agent_gw import AgentGwClient

    creds = _load_ifind_env()
    kwargs = {"timeout": TIMEOUT}
    if creds.get("KIMI_API_KEY"):
        kwargs["api_key"] = creds["KIMI_API_KEY"]
    if creds.get("KIMI_BASE_URL"):
        kwargs["base_url"] = creds["KIMI_BASE_URL"]
    return AgentGwClient(**kwargs)


def _call(client, api_name: str, params: dict) -> list[dict]:
    """调用 ifind API,把返回的 CSV 文件内容解析为行字典列表。"""
    payload = {"data_source_name": "ifind", "api_name": api_name, "params": params}
    resp = client.tools.call_data_source_tool(payload)
    raw = resp.raw
    if not raw.get("is_success"):
        error = raw.get("error") or {}
        raise RuntimeError(error.get("user") or error.get("assistant") or f"{api_name} 调用失败")
    rows: list[dict] = []
    for f in raw.get("files") or []:
        if isinstance(f, dict) and f.get("content"):
            rows.extend(csv.DictReader(io.StringIO(str(f["content"]))))
    return rows


def _num(row: dict, key: str) -> float | None:
    try:
        v = (row.get(key) or "").strip()
        return round(float(v), 4) if v else None
    except ValueError:
        return None


def _cached(path: Path) -> dict | None:
    if path.is_file() and time.time() - path.stat().st_mtime < CACHE_TTL_SECONDS:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None
    return None


async def get_fundamentals(symbol: str, kind: str = "stock") -> dict | None:
    """基本面快照;指数/非股票返回 None,调用失败抛 RuntimeError。"""
    import asyncio

    ticker = _ticker(symbol, kind)
    if ticker is None:
        return None

    CACHE_DIR.mkdir(exist_ok=True)
    cache_path = CACHE_DIR / f"{symbol}.json"
    hit = _cached(cache_path)
    if hit is not None:
        return hit

    def work() -> dict:
        with _client() as client:
            info_rows = _call(client, "ifind_get_stock_info", {
                "ticker": ticker, "file_path": f"/tmp/ifind_info_{symbol}.csv",
            })
            prof = grow = None
            period_used = None
            for period in _candidate_periods():
                rows = _call(client, "ifind_get_stock_financial_index", {
                    "ticker": ticker, "financial_parameter": period,
                    "category": "profitability", "file_path": f"/tmp/ifind_prof_{symbol}.csv",
                })
                if rows:
                    prof = rows[0]
                    period_used = period
                    break
            if period_used:
                rows = _call(client, "ifind_get_stock_financial_index", {
                    "ticker": ticker, "financial_parameter": period_used,
                    "category": "growth", "file_path": f"/tmp/ifind_grow_{symbol}.csv",
                })
                grow = rows[0] if rows else None

        info = info_rows[0] if info_rows else {}
        result = {
            "ticker": ticker,
            "source": "iFinD",
            "reportPeriod": period_used,
            "fetchedAt": int(time.time()),
            "profile": {
                "mainBusiness": (info.get("ths_main_businuess_stock") or "").strip(),
                "products": (info.get("ths_mo_product_name_stock") or "").strip(),
                "totalShares": _num(info, "ths_total_shares_stock"),
                "controller": (info.get("ths_actual_controller_stock") or "").strip(),
                "controllerType": (info.get("ths_actual_controller_type_stock") or "").strip(),
                "website": (info.get("ths_corp_website_stock") or "").strip(),
            },
            "profitability": {
                "roe": _num(prof, "ths_roe_stock") if prof else None,
                "grossMargin": _num(prof, "ths_gross_selling_rate_stock") if prof else None,
                "netMargin": _num(prof, "ths_net_sales_rate_stock") if prof else None,
                "eps": _num(prof, "ths_eps_basic_stock") if prof else None,
                "bps": _num(prof, "ths_nav_ps_stock") if prof else None,
            } if prof else None,
            "growth": {
                "revenueYoY": _num(grow, "ths_or_yoy_stock") if grow else None,
                "netProfitYoY": _num(grow, "ths_np_atsopc_yoy_stock") if grow else None,
            } if grow else None,
        }
        cache_path.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
        return result

    return await asyncio.to_thread(work)
