# alpha-desk 量化终端(terminal/)

把 dsh-alpha-desk 的投研 agent 能力装进一个同花顺风格的 Web 终端:左栏自选实时报价(红涨绿跌)、中间 DeepSeek agent 对话(走 risk-gate 风控,回复下方带**运行轨迹**——逐步思考/工具调用/token 计量)、底部 K 线(日K/60/15/5 分 + MA + 成交量)、右栏报价明细与 **专家团**(aihf 多大师信号面板)双 tab。

**只读研究终端:没有任何下单路径。** 数据为腾讯免费行情(分钟级延迟),所有 agent 回复仅供学习研究,不构成投资建议。

## 架构

```
浏览器 terminal/web (React + klinecharts v9)
   │ REST + WebSocket(localhost:8321)
FastAPI terminal/backend (python3.11 venv)
   ├── gateway_gtimg.py   腾讯行情 → vnpy BarData/TickData
   │                      (接口对齐 vnpy BaseGateway,未来 CTP/SimNow 可 drop-in)
   ├── market.py          自选缓存 + 15s 刷新 + WS 广播
   ├── agent_bridge.py    dsh --profile headless 子进程 + session 存档解析
   │                      (挂载 ../plugins/risk-gate,cwd=仓库根,alpha-desk skill 自动生效;
   │                       回复附带 trace:逐步 reasoning/tool-call/usage,来自 dsh 自身 session jsonl)
   ├── experts.py         aihf 专家团:多大师模型信号+理由,结构化返回;
   │                      未配 FINANCIAL_DATASETS_API_KEY/LLM key 时返回内置示例(demo=true 显式标注)
   └── watchlist.json     自选清单
```

为什么数据层直接调腾讯端点而不是 akshare 的东财接口:东财 `push2.eastmoney.com` 在部分网络下间歇性不可达,`qt.gtimg.cn` 稳定且支持股票+指数混合批量报价(一次请求刷完整个自选)。

## 运行

```bash
# 1) 后端(首次:brew install ta-lib && python3.11 -m venv terminal/.venv
#    && terminal/.venv/bin/pip install -r terminal/backend/requirements.txt)
cd terminal/backend
../.venv/bin/uvicorn app.main:app --port 8321

# 2) 前端(首次:cd terminal/web && npm install)
cd terminal/web
npm run dev        # 打开终端里显示的 localhost 地址
```

前置:dsh 已配置(`~/.dsh/settings.yaml` 有官方 provider + key),`alpha-desk` skill 已在 `~/.agents/skills/` 软链。

## API

| 端点 | 说明 |
|---|---|
| `GET /api/watchlist` | 自选+快照 |
| `PUT /api/watchlist` `{symbol, kind}` | 加自选(6 位代码) |
| `DELETE /api/watchlist/{symbol}` | 删自选 |
| `GET /api/quote/{symbol}` | 单票明细 |
| `GET /api/kline?symbol=&period=daily|60|30|15|5&count=` | K 线(vnpy BarData JSON) |
| `WS /ws/quotes` | 15s 推送自选快照 |
| `POST /api/chat` `{message, symbol?, symbol_name?}` | dsh agent 对话(超时 240s),返回 `{reply, trace}` |
| `POST /api/experts` `{tickers}` | 召开专家团(aihf 单周期,超时 600s;缺 key 时返回示例数据) |

## 产物

- `pitch/` — 介绍 PPT(PPTD 工程 + terminal-pitch.pptx,8 页:架构/四区/专家团/轨迹/合规/复现)
- `demo/alpha-desk-terminal-demo.mp4` — 49s 实操视频(报价→对话轨迹展开→专家团滚动)

## 已知边界

- 免费行情分钟级延迟,不做 tick 级;非交易时段显示最近收盘价
- 行情源故障时保留旧快照并在 `stale` 字段标记
- vnpy 完整安装含 PySide6(~500MB),只为它的数据模型与 Gateway 语义;若环境装不上 vnpy,backend 会自动回退到 `app/vnpy_compat.py`(暂未提供,需要时按 vnpy MIT 源码 vendor 四个定义即可)
