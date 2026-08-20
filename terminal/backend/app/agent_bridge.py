"""Bridge to the DeepSeek Harness agent.

Each chat message spawns one `dsh --profile headless` run with the alpha-desk
risk-gate patch mounted and the repo root as cwd (so the dsh-skill system picks
up the alpha-desk skill). Read-only by construction: the risk-gate plugin
intercepts any real-trading command before it can execute.

After the run, the bridge locates the session archive that dsh wrote under
$DSH_HOME/sessions and parses it into a trace: per-step reasoning, tool calls
(with arguments and results) and per-step token usage. This is what powers the
"agent 轨迹" timeline in the terminal UI.
"""
from __future__ import annotations

import asyncio
import json
import os
import time
from pathlib import Path

import zstandard

REPO_ROOT = Path(__file__).resolve().parents[3]
DSH_BIN = Path.home() / ".dsh/profiles/node_modules/@deepseek-ai/dsh/lib/bin.js"
RISK_GATE_PATCH = REPO_ROOT / "plugins/risk-gate/cordis.patch.yml"
IFIND_ENV = REPO_ROOT / "plugins/ifind/.env"
OPENCLAW_CONFIG = Path.home() / ".kimi_openclaw/openclaw.json"
TIMEOUT_SECONDS = 240


def _load_ifind_env() -> dict[str, str]:
    """Kimi agent-gw credentials for the iFinD datasource (plugins/ifind).

    Order: plugins/ifind/.env (gitignored) -> Kimi desktop's own kimi-coding
    key from ~/.kimi_openclaw/openclaw.json. Returned dict is overlaid on the
    dsh subprocess environment, so plugins/ifind/ifind_tool.py works inside
    agent runs without any manual key setup on this machine.
    """
    env: dict[str, str] = {}
    if IFIND_ENV.is_file():
        for line in IFIND_ENV.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip().strip('"').strip("'")
    if "KIMI_API_KEY" not in env and OPENCLAW_CONFIG.is_file():
        try:
            cfg = json.loads(OPENCLAW_CONFIG.read_text(encoding="utf-8"))
            key = cfg["models"]["providers"]["kimi-coding"]["apiKey"]
            base = cfg["models"]["providers"]["kimi-coding"]["baseUrl"]
            if key:
                env["KIMI_API_KEY"] = key
                env.setdefault("KIMI_BASE_URL", base)
        except (json.JSONDecodeError, KeyError, OSError):
            pass
    return env

DISCLAIMER = "本内容仅供学习研究,不构成投资建议。"

# dsh names the per-workspace session dir after the sanitized cwd.
SESSIONS_DIR = Path.home() / ".dsh/sessions/--Users-ahs-dsh-alpha-desk--"

MAX_REASONING_CHARS = 1200
MAX_RESULT_CHARS = 300


def _session_file_since(started_at: float) -> Path | None:
    """Newest session archive created for this run (mtime >= process start)."""
    if not SESSIONS_DIR.is_dir():
        return None
    candidates = [
        p for p in SESSIONS_DIR.glob("session-*/session.jsonl.zstd")
        if p.stat().st_mtime >= started_at - 1
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def _summarize_args(name: str, raw_arguments: str) -> str:
    try:
        args = json.loads(raw_arguments or "{}")
    except json.JSONDecodeError:
        return raw_arguments[:120]
    if name == "bash":
        return str(args.get("command", ""))[:160]
    if name == "skill":
        return str(args.get("name", ""))
    for key in ("path", "pattern", "file_path", "query", "url"):
        if key in args:
            return str(args[key])[:160]
    return raw_arguments[:120]


def _result_text(data: dict) -> str:
    """Pull plain text out of a tool/result event's nested content blocks."""
    texts: list[str] = []

    def walk(node: object) -> None:
        if isinstance(node, dict):
            if node.get("type") == "text" and isinstance(node.get("text"), str):
                texts.append(node["text"])
            else:
                for v in node.values():
                    walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(data.get("message", {}).get("content", []))
    return " ".join(texts).strip()


def parse_trace(session_file: Path, duration_ms: int) -> dict:
    """Parse a dsh session archive into a per-step trace with token usage."""
    dctx = zstandard.ZstdDecompressor()
    raw = dctx.stream_reader(session_file.open("rb")).read().decode("utf-8", errors="replace")

    steps: dict[int, dict] = {}
    calls_by_id: dict[str, dict] = {}
    model: str | None = None

    def step_of(n: int) -> dict:
        return steps.setdefault(n, {"step": n, "reasoning": "", "tools": [], "usage": None})

    for line in raw.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        etype, data = event.get("type"), event.get("data") or {}
        step_no = data.get("step")

        if etype == "request/header":
            model = (data.get("header") or {}).get("config", {}).get("model") or model
        elif etype == "step/start" and step_no is not None:
            step_of(step_no)
        elif etype == "reasoning-chunks" and step_no is not None:
            step_of(step_no)["reasoning"] += "".join(data.get("texts", []))
        elif etype == "tool/call" and step_no is not None:
            call = {
                "callId": data.get("callId", ""),
                "name": data.get("name", "?"),
                "summary": _summarize_args(data.get("name", ""), data.get("arguments", "")),
                "result": "",
            }
            step_of(step_no)["tools"].append(call)
            calls_by_id[call["callId"]] = call
        elif etype == "tool/result":
            call_id = ((data.get("message") or {}).get("source") or {}).get("callId")
            if call_id in calls_by_id:
                calls_by_id[call_id]["result"] = _result_text(data)[:MAX_RESULT_CHARS]
        elif etype == "assistant/chunk":
            chunk = data.get("chunk") or {}
            if chunk.get("type") == "usage" and step_no is not None:
                step_of(step_no)["usage"] = chunk.get("usage")

    step_list = sorted(steps.values(), key=lambda s: s["step"])
    for s in step_list:
        s["reasoning"] = s["reasoning"].strip()[:MAX_REASONING_CHARS]

    totals = {"inputTokens": 0, "outputTokens": 0, "cacheReadTokens": 0, "reasoningTokens": 0}
    tool_calls = 0
    for s in step_list:
        tool_calls += len(s["tools"])
        for k in totals:
            totals[k] += (s.get("usage") or {}).get(k, 0)
    totals["steps"] = len(step_list)
    totals["toolCalls"] = tool_calls

    return {"model": model, "durationMs": duration_ms, "steps": step_list, "totals": totals}


async def chat(message: str, symbol: str | None = None, symbol_name: str | None = None) -> dict:
    prompt = message
    if symbol:
        prompt = f"[量化终端上下文] 用户正在查看 {symbol_name or ''}({symbol}) 的行情。\n用户问题:{message}"
    lowered = message.lower()
    if "ifind" in lowered or "同花顺" in message:
        prompt += (
            "\n\n[系统提示] 本仓库 plugins/ifind/ifind_tool.py 可直接访问 iFinD"
            "(经 Kimi agent-gw,凭证已注入本进程环境,无需任何账号)。"
            "用法:先 `terminal/.venv/bin/python plugins/ifind/ifind_tool.py describe` 读 API 目录,"
            "再 `... call <api_name> --params-json '{...}'` 调用。"
            "禁止声称 iFinD 不可用或要求用户提供 iFinD 账号。"
        )

    started_at = time.time()
    cmd = ["node", str(DSH_BIN), "--profile", "headless",
           "--patch", str(RISK_GATE_PATCH), prompt]
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=REPO_ROOT,
        env={**os.environ, **_load_ifind_env()},
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        raise RuntimeError(f"agent 响应超时({TIMEOUT_SECONDS}s)")
    duration_ms = int((time.time() - started_at) * 1000)

    if proc.returncode != 0:
        detail = stderr.decode(errors="replace")[-500:]
        raise RuntimeError(f"agent 调用失败(exit {proc.returncode}): {detail}")

    reply = stdout.decode(errors="replace").strip()
    if "不构成投资建议" not in reply:
        reply += f"\n\n---\n{DISCLAIMER}"

    trace = None
    session_file = _session_file_since(started_at)
    if session_file:
        try:
            trace = parse_trace(session_file, duration_ms)
        except Exception:
            trace = None  # 轨迹解析失败不影响主回复

    return {"reply": reply, "trace": trace}
