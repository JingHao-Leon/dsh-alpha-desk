---
name: alpha-desk
description: AI 投研工作台——在 deepseek-harness 里编排 virattt/ai-hedge-fund（美股多策略 AI 基金，支持回测）与本地 A股/港股技术分析技能，配合 risk-gate 风控钩子、定时盯盘与投资记忆，完成"分析→回测→解读→复盘"的完整投研闭环。当用户要求分析美股、运行 AI 基金、回测策略、比较投资大师观点、生成投研报告、定时盯盘或复盘投资假设时使用。触发词：AI 基金、对冲基金、回测、巴菲特、格雷厄姆、投研、美股分析、盯盘、复盘。
---

# Alpha Desk — AI 投研工作台

把 dsh 会话变成一个投研交易台：底层引擎是 [virattt/ai-hedge-fund](https://github.com/virattt/ai-hedge-fund)（MIT，CLI 名 `aihf`），上层由 dsh 的 skill / hook / cron / memory 扩展点编排。

**硬性合规线（每次回复都要遵守）：**
- 本技能输出的是**研究与教育内容**，不是投资建议；每次给出结论时附上免责声明："本内容仅供学习研究，不构成投资建议。"
- **暂不执行真实交易**。risk-gate 插件会拦截实盘命令，但即使插件未安装，也不得运行任何券商下单、资金划转命令。用户要求实盘时，明确拒绝并说明原因。
- aihf 内部对 LLM 信号的调用本身会消耗用户的 LLM API 额度，运行前先告知。

## 前置条件检查（每次会话首次使用前执行）

```bash
command -v aihf && aihf --help | head -5
```

未安装则：`pipx install aihf`（或 `uv tool install aihf`）。

运行需要两类 key（导出在 shell 环境，或写入 `~/.hedge-fund/.env`）：
- `FINANCIAL_DATASETS_API_KEY` — 行情与基本面数据（financialdatasets.ai，有免费档）
- 一个 LLM key：`DEEPSEEK_API_KEY`（推荐，与 dsh 同栈）或 `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` / `GOOGLE_API_KEY` / `XAI_API_KEY` / `KIMI_API_KEY`

aihf 默认推理模型是 `claude-sonnet-5`（走 Anthropic）。用 DeepSeek 时，任选其一：
- `export HEDGE_FUND_LLM_MODEL=deepseek-v4-pro`（全局默认）
- 或在命令里加 `--model deepseek-v4-pro`（单次覆盖）

缺 key 时**停下来让用户提供**，不要伪造数据、不要编造回测结果。所有数字必须来自 aihf 的真实输出。

## 核心概念：mandate（基金委托书）

mandate 是一个 YAML，描述"交易台"本身——策略、投资大师模型、风控、资金、再平衡频率——**不含股票代码**；标的是运行时通过 `--tickers` 传入的。本仓库 `mandates/` 目录自带三份：

| 文件 | 风格 | 再平衡 | 适用场景 |
|---|---|---|---|
| `deep-value-weekly.yaml` | 格雷厄姆×2 + 巴菲特 + 芒格，70% 价值 + 30% 财报漂移量化 | weekly | 默认首选，稳健演示 |
| `fundamental-ls-market-neutral.yaml` | 五位大师投票的多空市场中性 | monthly | 展示多空推理 |
| `inflections-daily.yaml` | 德鲁肯米勒 + 林奇的宏观拐点 | daily | 压力测试风控 |

可用的 alpha 模型（`models[].name`）：`graham`、`buffett`、`munger`、`lynch`、`druckenmiller`（LLM 驱动）；`pead`（财报漂移，量化，不消耗 LLM 额度）。用户想自定义组合时，复制一份 mandate 改写即可。

## 工作流一：单次投研周期（"今天这只基金怎么看这几只票"）

```bash
aihf mandates/deep-value-weekly.yaml --tickers AAPL,MSFT,NVDA --out records/cycle-$(date +%F).json
```

- stdout 是纯 JSON（CycleRecord），人类摘要走 stderr；始终用 `--out` 落盘到 `records/` 供复盘。
- CycleRecord 关键字段：`strategies[].signals[]`（每个模型的 `value` ∈ [-1,1] 看多/看空强度 + `reasoning` 文字理由）、`positions`（成交后持股）、`equity_before`、`skipped`（数据缺失的票及原因）。
- 解读时：**先念各模型的 reasoning 原文要点，再给综合仓位变化**——"巴菲特为什么看多、格雷厄姆为什么反对"是用户最想看的。分歧要明确指出，不要和稀泥。

## 工作流二：回测（"这套策略过去一年表现如何"）

```bash
aihf mandates/deep-value-weekly.yaml --tickers AAPL,MSFT,NVDA --backtest --start 2025-08-01 --out records/backtest-$(date +%F).json
```

- 回测从 `--start` 到 `--date`（默认今天）按 mandate 的再平衡频率逐周期运行，输出含净值曲线与基准（mandate 里的 `benchmark`）对比指标。
- 解读必给：累计收益 vs 基准、最大回撤、胜率，以及**哪几次调仓贡献/拖累最大**（从逐周期记录里定位）。
- 回测耗 LLM 额度 = 周期数 × 模型数 × 标的数，运行前估算并告知用户（例：weekly × 52 周 × 3 个 LLM 模型 × 3 只票 ≈ 468 次调用）。想省钱就先缩短区间或减少模型。
- 明确提醒：历史回测不代表未来收益。

## 工作流三：A股/港股联动

aihf 只覆盖美股。用户问 A股/港股时，改用 `stock-technical-indicators` 技能（如已安装）。两边结果可以同框对比（例："同一套价值逻辑在美股和 A股各自选出什么"），但要讲清两边引擎和数据源不同，结论不可直接互换。

## 工作流四：定时盯盘（cron）

用户要求"每天盘前/盘后自动跑"时，用 dsh 的定时任务能力注册调度，例如：

- 美东盘前（北京时间 21:30 前）：跑工作流一，输出当日信号摘要
- 每周五收盘后：跑回测增量更新 + 本周假设复盘

定时任务产出的记录同样落盘 `records/`。

## 工作流五：投资记忆与复盘

- 每次给出一个观点时，把"假设"写进记忆：标的、方向、理由、预期时间窗、失效条件。
- 复盘时取出历史假设，对照 `records/` 里的实际信号与走势，逐条判定对错，并总结哪类假设胜率高。
- 这是本工作台区别于一次性问答的核心：**观点要被记录、被检验、被追责**。

## 失败处理

- `skipped` 非空 → 告知用户哪些票数据缺失（常见于新股、退市、数据源未覆盖），不要静默忽略。
- 报 `ANTHROPIC_API_KEY not found` 之类错误 → 说明用户没配 LLM key 或没指定模型；提示配 `DEEPSEEK_API_KEY` 并加 `--model deepseek-v4-pro`，不要擅自换成别的 provider。
- 网络/额度错误 → 原样报告 stderr，不要重试超过两次。
- 用户给的 mandate 路径不存在 → 先用 `ls mandates/` 列出可用的，让用户选。

## 安全红线（risk-gate 插件已装时由其强制执行，未装时自律）

- 禁止：任何券商 API/CLI 下单命令（ibkr、alpaca、tda、富途、老虎等）、向券商域名发写请求、`--live` 类参数。
- 禁止：修改 `~/.hedge-fund/.env` 之外的任何凭证文件。
- 允许：aihf 的全部只读/回测用法、数据查询、报告生成。
