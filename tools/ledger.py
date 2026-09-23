#!/usr/bin/env python3
"""公开预测台账（ledger）——观点先入库、到期机械结算。

每个预测是一条结构化 JSON：标的、方向（long/short/neutral）、置信度、到期日、理由。
`new` 落盘并 git commit（时间戳证据），`settle` 用真实收盘价按固定规则判 hit/miss，
无人工裁量；`report` 汇总胜率与置信度校准到 ledger/stats.md。

数据源（均免费无 key）：A股/港股/美股 腾讯 gtimg 日K（美股代码自动尝试 .OQ/.N 后缀）。
结算目录可用环境变量 LEDGER_DIR 覆盖（默认 <repo>/ledger），便于测试与演练。
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except AttributeError:
    pass

REPO_ROOT = Path(__file__).resolve().parent.parent
LEDGER_DIR = Path(os.environ.get("LEDGER_DIR", REPO_ROOT / "ledger"))
PRED_DIR = LEDGER_DIR / "predictions"
SETTLE_DIR = LEDGER_DIR / "settlements"
STATS_FILE = LEDGER_DIR / "stats.md"

GTIMG_KLINE = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
MARKETS = ("cn", "hk", "us")
DIRECTIONS = ("long", "short", "neutral")
LOOKBACK = 320          # 拉取的日K根数，覆盖一年左右
FINAL_GRACE_DAYS = 5    # horizon_end 之后最多等几个自然日仍视为"已到期可结算"


# ---------------------------------------------------------------- 数据抓取

def _http_get(url: str, timeout: float = 15.0) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "alpha-desk-ledger/1.0"})
    last_err: Exception | None = None
    for attempt in (1, 2):   # 网络抖动重试一次
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except OSError as e:
            last_err = e
            if attempt == 1:
                time.sleep(1.0)
    raise RuntimeError(f"行情请求失败: {last_err}")


def gtimg_code(symbol: str, market: str) -> str:
    if market == "hk":
        return "hk" + symbol.zfill(5)
    if market == "us":
        s = symbol.upper()
        return "us" + s if "." in s else f"us{s}.OQ"   # .OQ=纳斯达克 .N=纽交所
    return ("sh" if symbol.startswith(("6", "9")) else "sz") + symbol


def _gtimg_daily(code: str) -> dict[str, float]:
    fq = "qfq" if code.startswith(("sh", "sz")) else ""   # A股前复权，其余原始价
    url = GTIMG_KLINE + "?" + urllib.parse.urlencode(
        {"param": f"{code},day,,,{LOOKBACK},{fq}"})
    payload = json.loads(_http_get(url))
    if payload.get("code") != 0:
        raise RuntimeError(f"gtimg 错误: {payload.get('msg')}")
    node = payload["data"].get(code)
    if not node:
        raise RuntimeError(f"gtimg 未返回 {code} 的数据（检查标的代码）")
    rows = node.get("qfqday") or node.get("day") or []
    out = {}
    for row in rows:
        out[str(row[0])] = float(row[2])   # [date, open, close, high, low, volume]
    return out


def fetch_closes(symbol: str, market: str) -> dict[str, float]:
    """返回 {YYYY-MM-DD: close}。"""
    if market == "us" and "." not in symbol:
        # 未带后缀的美股代码：先按纳斯达克(.OQ)试，历史不足再按纽交所(.N)
        for suffix in (".OQ", ".N"):
            closes = _gtimg_daily(gtimg_code(symbol + suffix, market))
            if len(closes) >= 2:
                return closes
        raise RuntimeError(
            f"gtimg 上找不到 {symbol}（可显式带后缀，如 {symbol}.OQ 或 {symbol}.N）")
    closes = _gtimg_daily(gtimg_code(symbol, market))
    if not closes:
        raise RuntimeError(f"gtimg 返回 {symbol} 日K为空")
    return closes


def close_on_or_after(closes: dict[str, float], date: str) -> tuple[str, float]:
    """基线：as_of 当日或之后首个交易日收盘。"""
    for day in sorted(closes):
        if day >= date:
            return day, closes[day]
    raise RuntimeError(f"{date} 之后没有任何收盘数据")


def close_on_or_before(closes: dict[str, float], date: str) -> tuple[str, float]:
    """终值：horizon_end 当日或之前最近交易日收盘。"""
    for day in sorted(closes, reverse=True):
        if day <= date:
            return day, closes[day]
    raise RuntimeError(f"{date} 之前没有任何收盘数据")


# ---------------------------------------------------------------- 校验与落盘

def validate(pred: dict) -> None:
    if pred["direction"] not in DIRECTIONS:
        raise ValueError(f"direction 必须是 {DIRECTIONS}")
    conf = float(pred["confidence"])
    if not 0.0 < conf <= 1.0:
        raise ValueError("confidence 必须在 (0, 1]")
    asset = pred["asset"]
    if asset["market"] not in MARKETS:
        raise ValueError(f"market 必须是 {MARKETS}")
    as_of = dt.date.fromisoformat(pred["as_of"])
    horizon = dt.date.fromisoformat(pred["horizon_end"])
    if horizon <= as_of:
        raise ValueError("horizon_end 必须晚于 as_of")
    if not pred.get("rationale", "").strip():
        raise ValueError("rationale 不能为空——没有理由的观点不入台账")
    if asset["market"] in ("cn", "hk") and not asset["symbol"].isdigit():
        raise ValueError("A股/港股 symbol 必须是纯数字代码")


def pred_id(pred: dict) -> str:
    return f"{pred['as_of'].replace('-', '')}-{pred['asset']['symbol']}-{pred['direction']}"


def commit(paths: list[Path], message: str) -> bool:
    """git add + commit；不在 git 仓库里时静默跳过（演练模式）。"""
    try:
        subprocess.run(["git", "add", *[str(p.relative_to(REPO_ROOT)) for p in paths]],
                       cwd=REPO_ROOT, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", message],
                       cwd=REPO_ROOT, check=True, capture_output=True)
        return True
    except (subprocess.CalledProcessError, ValueError):
        return False


# ---------------------------------------------------------------- 子命令

def cmd_new(args) -> int:
    as_of = args.as_of or dt.date.today().isoformat()
    pred = {
        "id": "",
        "created_at": dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds"),
        "asset": {"symbol": args.symbol, "market": args.market, "name": args.name or ""},
        "direction": args.direction,
        "confidence": round(args.confidence, 2),
        "as_of": as_of,
        "horizon_end": args.horizon_end,
        "deadband": args.deadband,
        "rationale": args.rationale,
        "invalidate_if": args.invalidate_if or "",
        "source": args.source or "",
        "status": "open",
    }
    validate(pred)
    pred["id"] = pred_id(pred)
    PRED_DIR.mkdir(parents=True, exist_ok=True)
    path = PRED_DIR / f"{pred['id']}.json"
    n = 2
    while path.exists():
        pred["id"] = f"{pred_id(pred).rsplit('-', 1)[0]}-{args.direction}-{n}"
        path = PRED_DIR / f"{pred['id']}.json"
        n += 1
    path.write_text(json.dumps(pred, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"已写入 {path}")
    if not args.no_commit:
        ok = commit([path], f"ledger: predict {pred['id']} "
                    f"({args.direction} {args.symbol} conf={pred['confidence']} "
                    f"→ {args.horizon})")
        print("已 git commit（记得尽快 push，公开时间戳才成立）" if ok
              else "未 commit（不在 git 仓库或无变更），请手动处理")
    return 0


def settle_one(pred: dict, force: bool = False) -> dict:
    """对单个预测做机械结算，返回 settlement dict（不落盘）。"""
    symbol = pred["asset"]["symbol"]
    market = pred["asset"]["market"]
    closes = fetch_closes(symbol, market)
    base_day, base_close = close_on_or_after(closes, pred["as_of"])
    end_day, end_close = close_on_or_before(closes, pred["horizon_end"])
    horizon = dt.date.fromisoformat(pred["horizon_end"])
    if end_day < pred["horizon_end"] and dt.date.today() < horizon + dt.timedelta(days=FINAL_GRACE_DAYS):
        if not force:
            raise RuntimeError(
                f"最终收盘价尚未产生（数据最新到 {end_day}，horizon_end={pred['horizon_end']}）；"
                f"确认已到期可用 --force")
    ret = end_close / base_close - 1.0
    band = float(pred.get("deadband", 0.005))
    direction = pred["direction"]
    if direction == "long":
        outcome = "hit" if ret > band else "miss"
    elif direction == "short":
        outcome = "hit" if ret < -band else "miss"
    else:
        outcome = "hit" if abs(ret) <= band else "miss"
    return {
        "id": pred["id"],
        "settled_at": dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds"),
        "rule": f"baseline={base_day} close, final={end_day} close, deadband={band}",
        "baseline": {"date": base_day, "close": base_close},
        "final": {"date": end_day, "close": end_close},
        "return": round(ret, 6),
        "direction": direction,
        "confidence": pred["confidence"],
        "outcome": outcome,
    }


def cmd_settle(args) -> int:
    PRED_DIR.mkdir(parents=True, exist_ok=True)
    SETTLE_DIR.mkdir(parents=True, exist_ok=True)
    today = dt.date.today().isoformat()
    targets = []
    for path in sorted(PRED_DIR.glob("*.json")):
        pred = json.loads(path.read_text(encoding="utf-8"))
        if args.id and pred["id"] != args.id:
            continue
        if pred["status"] != "open":
            continue
        if not args.force and pred["horizon_end"] > today:
            continue
        targets.append((path, pred))
    if not targets:
        print("没有待结算的到期预测")
        return 0

    committed_files = []
    for path, pred in targets:
        try:
            settlement = settle_one(pred, force=args.force)
        except (RuntimeError, ValueError) as e:
            print(f"[跳过] {pred['id']}: {e}")
            continue
        settle_path = SETTLE_DIR / f"{pred['id']}.json"
        settle_path.write_text(
            json.dumps(settlement, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        pred["status"] = "settled"
        path.write_text(json.dumps(pred, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        ret = settlement["return"]
        print(f"[{settlement['outcome'].upper():4}] {pred['id']}  "
              f"{settlement['baseline']['close']} → {settlement['final']['close']}  "
              f"ret={ret:+.2%}")
        committed_files.extend([path, settle_path])
    if committed_files and not args.no_commit:
        if commit(committed_files, f"ledger: settle {len(targets)} prediction(s)"):
            print("已 git commit（记得尽快 push）")
    return 0


def cmd_report(args) -> int:
    settlements = []
    if SETTLE_DIR.exists():
        for path in sorted(SETTLE_DIR.glob("*.json")):
            settlements.append(json.loads(path.read_text(encoding="utf-8")))
    lines = ["# 台账战绩", "",
             "由 `tools/ledger.py report --write` 自动生成，勿手改。", ""]
    if not settlements:
        lines += ["台账自运行起暂无已结算预测。所有战绩只能来自真实结算累积，"
                  "不接受任何形式的回填。", ""]
    else:
        scored = [s for s in settlements if s["outcome"] in ("hit", "miss")]
        voided = [s for s in settlements if s["outcome"] == "void"]
        hits = sum(1 for s in scored if s["outcome"] == "hit")
        n = len(scored)
        lines += [
            f"- 已结算 **{n}** 条（另有 {len(voided)} 条数据缺失作废），"
            f"命中 **{hits}**，胜率 **{hits / n:.0%}**" if n else "- 暂无可计分结算",
            f"- 平均方向收益 **{sum(s['return'] for s in scored) / n:+.2%}**" if n else "",
            "",
            "## 置信度校准", "",
            "| 声明置信度 | 条数 | 实际命中率 |",
            "|---|---|---|",
        ]
        buckets: dict[float, list[dict]] = {}
        for s in scored:
            buckets.setdefault(round(float(s["confidence"]) * 10) / 10, []).append(s)
        for level in sorted(buckets):
            group = buckets[level]
            g_hits = sum(1 for s in group if s["outcome"] == "hit")
            lines.append(f"| {level:.1f} | {len(group)} | {g_hits / len(group):.0%} |")
        lines += ["", "## 明细", "",
                  "| id | 方向 | 置信度 | 区间收益 | 结果 |",
                  "|---|---|---|---|---|"]
        for s in settlements:
            lines.append(f"| {s['id']} | {s['direction']} | {s['confidence']} "
                         f"| {s['return']:+.2%} | {s['outcome']} |")
        lines.append("")
    text = "\n".join(line for line in lines if line is not None)
    if args.write:
        STATS_FILE.write_text(text, encoding="utf-8")
        print(f"已写入 {STATS_FILE}")
    else:
        print(text)
    return 0


def cmd_verify(args) -> int:
    closes = fetch_closes(args.symbol, args.market)
    days = sorted(closes)[-5:]
    print(f"{args.market}:{args.symbol} 最近 {len(days)} 个交易日收盘（数据源 gtimg）:")
    for day in days:
        print(f"  {day}  {closes[day]}")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="公开预测台账：预测入库 / 到期机械结算 / 战绩汇总")
    sub = p.add_subparsers(dest="cmd", required=True)

    pn = sub.add_parser("new", help="登记一条预测并 commit")
    pn.add_argument("--symbol", required=True)
    pn.add_argument("--market", default="cn", choices=MARKETS)
    pn.add_argument("--name", default="")
    pn.add_argument("--direction", required=True, choices=DIRECTIONS)
    pn.add_argument("--confidence", type=float, required=True)
    pn.add_argument("--as-of", default=None, help="基线日，默认今天")
    pn.add_argument("--horizon", required=True, dest="horizon_end", help="到期日 YYYY-MM-DD")
    pn.add_argument("--deadband", type=float, default=0.005)
    pn.add_argument("--rationale", required=True)
    pn.add_argument("--invalidate-if", default="")
    pn.add_argument("--source", default="", help="产生该观点的工作流/mandate")
    pn.add_argument("--no-commit", action="store_true")
    pn.set_defaults(func=cmd_new)

    ps = sub.add_parser("settle", help="结算所有到期的 open 预测")
    ps.add_argument("--id", default=None, help="只结算指定 id")
    ps.add_argument("--force", action="store_true", help="跳过到期宽限检查（历史演练用）")
    ps.add_argument("--no-commit", action="store_true")
    ps.set_defaults(func=cmd_settle)

    pr = sub.add_parser("report", help="生成战绩汇总")
    pr.add_argument("--write", action="store_true", help="写入 ledger/stats.md")
    pr.set_defaults(func=cmd_report)

    pv = sub.add_parser("verify", help="检查行情数据通路")
    pv.add_argument("--symbol", required=True)
    pv.add_argument("--market", default="cn", choices=MARKETS)
    pv.set_defaults(func=cmd_verify)

    args = p.parse_args(argv)
    try:
        return args.func(args)
    except (RuntimeError, ValueError) as e:
        print(f"错误: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
