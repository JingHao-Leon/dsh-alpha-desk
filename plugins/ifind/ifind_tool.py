#!/usr/bin/env python3
"""Query iFinD financial data through Kimi's agent-gw data-source API.

Thin CLI wrapper so agents can discover and call iFinD APIs without any
iFinD account — auth is a Kimi key (KIMI_API_KEY env or ~/.kimi/agent-gw.json;
the terminal backend auto-fills it from the local Kimi desktop config).

Usage:
  ifind_tool.py describe                      # print the API catalog (read first!)
  ifind_tool.py call <api_name> [--params-json '{}'] [--params-file f.json]

Requires the agent-gw SDK (see plugins/ifind/README.md for the install line).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

DATA_SOURCE = "ifind"
TIMEOUT = 60.0

PLUGIN_ENV = Path(__file__).resolve().parent / ".env"
OPENCLAW_CONFIG = Path.home() / ".kimi_openclaw/openclaw.json"


def _resolve_credentials() -> dict:
    """Kimi agent-gw 凭证自解析(dsh bash 工具的环境被净化,不能依赖环境变量注入)。

    顺序:plugins/ifind/.env -> ~/.kimi_openclaw/openclaw.json 的 kimi-coding key。
    都没找到时返回空 dict,由 agent-gw SDK 走自己的默认链(KIMI_API_KEY /
    ~/.kimi/agent-gw.json)并报错。
    """
    creds: dict = {}
    if PLUGIN_ENV.is_file():
        for line in PLUGIN_ENV.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                creds[k.strip()] = v.strip().strip('"').strip("'")
    if "KIMI_API_KEY" not in creds and OPENCLAW_CONFIG.is_file():
        try:
            cfg = json.loads(OPENCLAW_CONFIG.read_text(encoding="utf-8"))
            provider = cfg["models"]["providers"]["kimi-coding"]
            if provider.get("apiKey"):
                creds["KIMI_API_KEY"] = provider["apiKey"]
                creds.setdefault("KIMI_BASE_URL", provider.get("baseUrl", ""))
        except (json.JSONDecodeError, KeyError, OSError):
            pass
    return creds


def _client():
    try:
        from agent_gw import AgentGwClient, AgentGwError
    except ModuleNotFoundError:
        raise SystemExit(
            "缺少 agent-gw SDK,安装:python3 -m pip install \"$(curl -s "
            "https://cdn.kimi.com/agentgw/pysdk/manifest.json | python3 -c "
            "\"import json,sys; print(json.load(sys.stdin)['latest']['url'])\")\""
        )
    creds = _resolve_credentials()
    kwargs = {"timeout": TIMEOUT}
    if creds.get("KIMI_API_KEY"):
        kwargs["api_key"] = creds["KIMI_API_KEY"]
    if creds.get("KIMI_BASE_URL"):
        kwargs["base_url"] = creds["KIMI_BASE_URL"]
    return AgentGwClient(**kwargs), AgentGwError


def cmd_describe() -> int:
    client, err_cls = _client()
    try:
        with client as c:
            resp = c.tools.get_data_source_desc({"name": DATA_SOURCE})
            resp.raise_for_status()
            print(resp.text)
    except err_cls as exc:
        print(f"获取 ifind 数据源描述失败: {exc}", file=sys.stderr)
        return 1
    return 0


def cmd_call(api_name: str, params: dict) -> int:
    client, err_cls = _client()
    payload = {"data_source_name": DATA_SOURCE, "api_name": api_name, "params": params}
    try:
        with client as c:
            resp = c.tools.call_data_source_tool(payload)
    except err_cls as exc:
        print(f"调用 {api_name} 失败: {exc}", file=sys.stderr)
        return 1

    raw = resp.raw
    if not raw.get("is_success"):
        error = raw.get("error") or {}
        msg = error.get("user") or error.get("assistant") or "未知错误"
        print(f"{api_name} 返回错误: {msg}", file=sys.stderr)
        return 1

    for f in raw.get("files") or []:
        if isinstance(f, dict) and f.get("name"):
            p = Path(str(f["name"]))
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(str(f.get("content", "")), encoding="utf-8")

    result = raw.get("result") or {}
    texts = result.get("assistant")
    if isinstance(texts, list):
        print("\n".join(str(t) for t in texts))
    elif texts is not None:
        print(texts)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("describe", help="打印 ifind 数据源 API 目录(调用前必读)")
    call = sub.add_parser("call", help="调用指定 API")
    call.add_argument("api_name")
    call.add_argument("--params-json", default=None)
    call.add_argument("--params-file", default=None)
    args = parser.parse_args()

    if args.command == "describe":
        return cmd_describe()

    if args.params_json and args.params_file:
        raise SystemExit("--params-json 与 --params-file 只能用一个")
    params = {}
    if args.params_file:
        params = json.loads(Path(args.params_file).read_text(encoding="utf-8"))
    elif args.params_json:
        params = json.loads(args.params_json)
    if not isinstance(params, dict):
        raise SystemExit("params 必须是 JSON 对象")
    return cmd_call(args.api_name, params)


if __name__ == "__main__":
    sys.exit(main())
