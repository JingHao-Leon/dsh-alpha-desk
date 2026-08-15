# Alpha Desk — deepseek-harness 的 AI 投研工作台

[English](README.en.md) | 中文

> 把 [deepseek-harness](https://github.com/deepseek-ai/deepseek-harness)（dsh）会话变成一个投研交易台：
> 多策略 AI 基金回测 + A股/港股技术分析 + 风控合规门禁 + 定时盯盘 + 投资记忆复盘。
> 本仓库是一个可直接安装的 dsh **skill 包**，也是 dsh 微内核扩展点（skill / hook / cron / memory）的完整示范。

**免责声明：本项目仅供学习研究，不构成投资建议，不执行真实交易。**

## 它解决什么问题

通用 agent 框架能"聊天"，但做投研缺四样东西：

1. **可复现的引擎** —— 结论不能是模型即兴编的，必须来自真实数据与真实计算
2. **合规边界** —— agent 权限越来越大，"永远碰不到真钱"要是架构保证，不是提示词约定
3. **持续性** —— 投资观点要被记录、被定时检验、被事后追责
4. **多市场** —— 美股、A股、港股各一套数据与逻辑

Alpha Desk 用 dsh 的四个扩展点各解决一个问题：

| 问题 | dsh 扩展点 | 本仓库实现 |
|---|---|---|
| 可复现引擎 | skill（`section` + `inject()`） | [`skill/SKILL.md`](skill/SKILL.md)：编排 [virattt/ai-hedge-fund](https://github.com/virattt/ai-hedge-fund) CLI，stdout 纯 JSON，全部落盘 |
| 合规边界 | hook（`tools/pre-execute` waterfall） | [`plugins/risk-gate`](plugins/risk-gate/index.ts)：实盘下单/券商 API/凭证访问在分发前被单调拒绝 |
| 持续性 | cron + memory | SKILL.md 工作流四/五：盘前扫描、周末复盘、假设台账 |
| 多市场 | skill 组合 | 美股走 aihf；A股/港股联动 `stock-technical-indicators` 技能 |

## 架构

```
用户（自然语言）
   │
   ▼
deepseek-harness agent ── inject ──► skill/SKILL.md（本仓库）
   │                                   │
   │   tools/pre-execute               ▼
   │ ◄── risk-gate 插件（拒绝实盘）   aihf CLI（ai-hedge-fund 引擎）
   │                                   │  stdout: CycleRecord / BacktestResult JSON
   │                                   ▼
   │                              records/*.json（落盘，供复盘）
   │
   ├── cron：盘前/周末定时触发投研工作流
   └── memory：投资假设台账，到期对照 records 复盘
```

底层引擎 [ai-hedge-fund](https://github.com/virattt/ai-hedge-fund)（MIT）把"基金"做成声明式 mandate：策略 pod、投资大师 alpha 模型（格雷厄姆/巴菲特/芒格/林奇/德鲁肯米勒 + 量化 PEAD）、风控限额、再平衡频率都是 YAML 数据；标的在运行时通过 `--tickers` 传入。aihf 原生支持 **DeepSeek 作为推理 LLM**——DeepSeek 模型跑在 DeepSeek harness 里驱动 AI 基金，全栈同构。

## 量化终端（terminal/）

把上面的 agent 能力装进一个同花顺风格的 Web 终端——A股自选实时报价、K线、右栏明细，中间是对话区,所有回复都过 risk-gate:

![alpha-desk 量化终端](terminal/screenshot.png)

数据层用 **vnpy** 的 BarData/TickData 对象模型与 Gateway 语义封装腾讯免费行情(分钟级延迟),未来换 CTP/SimNow 是 drop-in 替换;agent 走 `dsh --profile headless` + risk-gate patch。**只读研究终端,没有下单路径。** 安装与 API 详见 [terminal/README.md](terminal/README.md)。

## 快速开始

```bash
# 1. 安装引擎（pipx 隔离安装）
pipx install aihf

# 2. 配置 key（二选一：shell 环境变量，或写入 ~/.hedge-fund/.env）
export FINANCIAL_DATASETS_API_KEY=...   # 行情与基本面，financialdatasets.ai 有免费档
export DEEPSEEK_API_KEY=...             # alpha 模型的推理 LLM

# 3. 手动验证引擎
aihf mandates/deep-value-weekly.yaml --tickers AAPL,MSFT,NVDA --backtest

# 4. 把 skill 装进 dsh（按你的 dsh 安装方式，将 skill/ 目录加入技能搜索路径，
#    例如软链到 ~/.agents/skills/alpha-desk）
ln -s "$PWD/skill" ~/.agents/skills/alpha-desk

# 5. （可选但推荐）启用 risk-gate 插件，见 plugins/risk-gate/
```

然后在 dsh 里直接说人话：

- 「用深度价值基金回测一下苹果、微软、英伟达过去一年」
- 「巴菲特和格雷厄姆对 NVDA 的看法有什么分歧？」
- 「每个交易日盘前帮我跑一遍持仓信号」
- 「上周你建议关注的几只票，现在复盘一下对错」

## 仓库结构

```
dsh-alpha-desk/
├── skill/SKILL.md                        # dsh 技能本体（触发条件、工作流、合规红线）
├── mandates/                             # 三份开箱即用的基金委托书
│   ├── deep-value-weekly.yaml            #   深度价值（格雷厄姆×2+巴菲特+芒格）周频
│   ├── fundamental-ls-market-neutral.yaml #  五大师多空市场中性，月频
│   └── inflections-daily.yaml            #   宏观拐点（德鲁肯米勒+林奇）日频
├── plugins/risk-gate/                    # dsh 风控钩子插件（tools/pre-execute）
├── terminal/                             # 同花顺风格量化终端（vnpy 数据层 + FastAPI + React）
│   ├── backend/app/gateway_gtimg.py      #   腾讯行情 → vnpy BarData/TickData
│   ├── backend/app/agent_bridge.py       #   dsh headless 桥（risk-gate 已挂载）
│   └── web/                              #   React + klinecharts 终端 UI
├── records/                              # 运行记录落盘目录（git 忽略）
└── LICENSE                               # MIT
```

## 与主流 agent 框架的对比

| 能力 | Alpha Desk (dsh) | 裸 LangChain/CrewAI 编排 | 通用编码 agent + 提示词 |
|---|---|---|---|
| 合规边界 | 架构级：hook 在工具分发前单调拒绝 | 需自己包一层执行器 | 仅靠提示词，模型可绕过 |
| 投研引擎 | 成熟开源基金引擎，JSON 可复现 | 自行拼装 | 模型即兴生成，不可复现 |
| 定时盯盘 | dsh cron 扩展点，声明式 | 需外部调度器 | 无 |
| 观点追责 | memory + 落盘记录，到期自动复盘 | 自行实现状态层 | 无 |
| 热重载/生态 | dsh 插件 HMR，MCP/skill 生态复用 | — | — |

## 致谢与边界

- 引擎：[virattt/ai-hedge-fund](https://github.com/virattt/ai-hedge-fund)（MIT），本项目只做编排层，不 fork 其代码；其数据源 Financial Datasets 主要覆盖美股
- 运行时：[deepseek-ai/deepseek-harness](https://github.com/deepseek-ai/deepseek-harness)
- 数据源覆盖不了 A股/港股；回测结果不代表未来收益；本项目永不执行真实交易
