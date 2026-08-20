# plugins/ifind — iFinD 数据源(经 Kimi agent-gw)

让 agent 免 iFinD 账号查询同花顺 iFinD 数据:行情(实时/历史)、财务报表、
经营分部、公告、股东、业绩预测、智能选股(A股/港股/美股)。
鉴权用的是本机 Kimi 桌面端的 key,走 Kimi agent-gw 转发,不是同花顺官方
iFinD MCP(那个需要 iFinD 终端密钥,本项目未采用)。

## 一次性安装(agent-gw SDK,装进终端 venv)

```bash
terminal/.venv/bin/pip install "$(curl -s https://cdn.kimi.com/agentgw/pysdk/manifest.json \
  | python3 -c "import json,sys; print(json.load(sys.stdin)['latest']['url'])")"
```

## 密钥解析顺序(脚本自行解析,不依赖环境变量)

1. `plugins/ifind/.env`(gitignored,见 `.env.example`)里的 `KIMI_API_KEY` / `KIMI_BASE_URL`
2. 自动读 `~/.kimi_openclaw/openclaw.json` 的 kimi-coding key(Kimi 桌面端自带)
3. agent-gw SDK 默认链:`KIMI_API_KEY` 环境变量 / `~/.kimi/agent-gw.json`

注意:dsh 的 bash 工具会净化环境变量,所以凭证解析做在脚本内部,
agent 直接运行脚本即可,无需任何 export。

## 用法(agent 经 bash 工具调用,必须用 venv python)

```bash
# 1. 先读 API 目录(9 个 API 的参数约定)
terminal/.venv/bin/python plugins/ifind/ifind_tool.py describe

# 2. 按目录里的参数约定调用
terminal/.venv/bin/python plugins/ifind/ifind_tool.py call ifind_get_stock_realtime_price \
  --params-json '{"ticker": "600519.SH"}'
```

可用 API:`ifind_get_stock_realtime_price` / `ifind_get_stock_info` /
`ifind_get_stock_business_segmentation` / `ifind_get_financial_statements` /
`ifind_get_stock_financial_index` / `ifind_get_price` / `ifind_get_forecast` /
`ifind_get_stock_announcement` / `ifind_get_holder_info`

注意:公告与业绩预测仅覆盖 A 股;ticker 格式 A股 `XXXXXX.SH/SZ/BJ`、
港股 `XXXX.HK`、美股 `XXXX.O/N/A`。数据为第三方市场数据,回答时带上
报告期/币种/覆盖范围等限定语。
