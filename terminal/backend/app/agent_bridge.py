"""Bridge to the DeepSeek Harness agent.

Each chat message spawns one `dsh --profile headless` run with the alpha-desk
risk-gate patch mounted and the repo root as cwd (so the dsh-skill system picks
up the alpha-desk skill). Read-only by construction: the risk-gate plugin
intercepts any real-trading command before it can execute.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
DSH_BIN = Path.home() / ".dsh/profiles/node_modules/@deepseek-ai/dsh/lib/bin.js"
RISK_GATE_PATCH = REPO_ROOT / "plugins/risk-gate/cordis.patch.yml"
TIMEOUT_SECONDS = 240

DISCLAIMER = "本内容仅供学习研究，不构成投资建议。"


async def chat(message: str, symbol: str | None = None, symbol_name: str | None = None) -> str:
    prompt = message
    if symbol:
        prompt = f"[量化终端上下文] 用户正在查看 {symbol_name or ''}({symbol}) 的行情。\n用户问题:{message}"

    proc = await asyncio.create_subprocess_exec(
        "node", str(DSH_BIN),
        "--profile", "headless",
        "--patch", str(RISK_GATE_PATCH),
        prompt,
        cwd=REPO_ROOT,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        raise RuntimeError(f"agent 响应超时({TIMEOUT_SECONDS}s)")

    if proc.returncode != 0:
        detail = stderr.decode(errors="replace")[-500:]
        raise RuntimeError(f"agent 调用失败(exit {proc.returncode}): {detail}")

    reply = stdout.decode(errors="replace").strip()
    if "不构成投资建议" not in reply:
        reply += f"\n\n---\n{DISCLAIMER}"
    return reply
