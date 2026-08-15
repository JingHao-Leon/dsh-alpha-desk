"""Expert panel ("专家团"): run one aihf (ai-hedge-fund) cycle and surface each
model's signal + reasoning, grouped by expert.

Live mode requires FINANCIAL_DATASETS_API_KEY plus one LLM key (in the
environment or ~/.hedge-fund/.env). Without keys we serve a bundled sample
record flagged demo=true so the UI is still explorable — the sample is clearly
labeled and never presented as a real signal.
"""
from __future__ import annotations

import asyncio
import json
import os
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_MANDATE = REPO_ROOT / "mandates/deep-value-weekly.yaml"
RECORDS_DIR = REPO_ROOT / "records"
SAMPLE_CYCLE = Path(__file__).with_name("sample_cycle.json")
HEDGE_ENV = Path.home() / ".hedge-fund/.env"
TIMEOUT_SECONDS = 600

LLM_KEYS = (
    "DEEPSEEK_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY",
    "GOOGLE_API_KEY", "XAI_API_KEY", "KIMI_API_KEY",
)

MODEL_LABELS = {
    "graham": "格雷厄姆",
    "buffett": "巴菲特",
    "munger": "芒格",
    "lynch": "彼得·林奇",
    "druckenmiller": "德鲁肯米勒",
    "pead": "财报漂移(量化)",
}


def _keys_ready() -> bool:
    if os.environ.get("FINANCIAL_DATASETS_API_KEY") and any(os.environ.get(k) for k in LLM_KEYS):
        return True
    return HEDGE_ENV.is_file()  # aihf 自己会读这个文件


def _load_sample(tickers: list[str]) -> dict:
    data = json.loads(SAMPLE_CYCLE.read_text(encoding="utf-8"))
    data["demo"] = True
    data["tickers"] = tickers
    data["note"] = (
        "未检测到 FINANCIAL_DATASETS_API_KEY / LLM key,当前为内置示例数据。"
        "配好 key(见 skill/SKILL.md 前置条件)后重新召开即为真实专家团信号。"
    )
    return data


def _normalize(record: dict, tickers: list[str]) -> dict:
    """CycleRecord -> {experts: [{model, label, signals: [{ticker, value, reasoning}]}]}"""
    by_model: dict[str, dict] = {}
    for strat in record.get("strategies", []):
        for sig in strat.get("signals", []):
            name = sig.get("model") or sig.get("name") or sig.get("agent") or "unknown"
            entry = by_model.setdefault(name, {
                "model": name,
                "label": MODEL_LABELS.get(name, name),
                "signals": [],
            })
            entry["signals"].append({
                "ticker": sig.get("ticker") or sig.get("symbol") or "?",
                "value": sig.get("value", 0),
                "reasoning": sig.get("reasoning") or sig.get("rationale") or "",
            })
    experts = sorted(by_model.values(), key=lambda e: e["model"])
    return {
        "demo": False,
        "tickers": tickers,
        "experts": experts,
        "positions": record.get("positions", []),
        "skipped": record.get("skipped", []),
        "asOf": record.get("date") or time.strftime("%Y-%m-%d"),
    }


async def run_experts(tickers: list[str]) -> dict:
    tickers = [t.strip().upper() for t in tickers if t.strip()][:8]
    if not tickers:
        raise RuntimeError("至少需要一个 ticker")
    if not _keys_ready():
        return _load_sample(tickers)

    RECORDS_DIR.mkdir(exist_ok=True)
    out = RECORDS_DIR / f"experts-{int(time.time())}.json"
    proc = await asyncio.create_subprocess_exec(
        "aihf", str(DEFAULT_MANDATE),
        "--tickers", ",".join(tickers),
        "--model", "deepseek-v4-pro",
        "--out", str(out),
        cwd=REPO_ROOT,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        raise RuntimeError(f"专家团运行超时({TIMEOUT_SECONDS}s)")

    if proc.returncode != 0:
        detail = stderr.decode(errors="replace")[-400:]
        raise RuntimeError(f"aihf 运行失败(exit {proc.returncode}): {detail}")

    record_text = out.read_text(encoding="utf-8") if out.is_file() else stdout.decode(errors="replace")
    record = _normalize(json.loads(record_text), tickers)
    record["record_file"] = str(out.relative_to(REPO_ROOT))
    return record
