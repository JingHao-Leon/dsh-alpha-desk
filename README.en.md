# Alpha Desk — an AI Investment Desk for deepseek-harness

English | [中文](README.md)

> Turns a [deepseek-harness](https://github.com/deepseek-ai/deepseek-harness) (dsh) session into an investment research desk:
> multi-strategy AI fund backtesting + China A/H-share technical analysis + a compliance gate + scheduled monitoring + investment memory.
> This repo is an installable dsh **skill pack**, and a complete demonstration of dsh's microkernel extension points (skill / hook / cron / memory).

**Disclaimer: for education and research only. Not investment advice. This project does not execute real trades for now.**

## What it solves

General-purpose agent frameworks can chat, but investment research needs four more things:

1. **A reproducible engine** — conclusions must come from real data and real computation, not improvised by the model
2. **A compliance boundary** — as agents gain power, "can never touch real money" must be an architectural guarantee, not a prompt convention
3. **Persistence** — investment theses should be recorded, re-checked on a schedule, and held accountable
4. **Multi-market coverage** — US, A-shares and HK shares each have their own data and logic

Alpha Desk maps one dsh extension point to each problem:

| Problem | dsh extension point | Implementation here |
|---|---|---|
| Reproducible engine | skill (`section` + `inject()`) | [`skill/SKILL.md`](skill/SKILL.md): orchestrates the [virattt/ai-hedge-fund](https://github.com/virattt/ai-hedge-fund) CLI; pure JSON on stdout, everything persisted |
| Compliance boundary | hook (`tools/pre-execute` waterfall) | [`plugins/risk-gate`](plugins/risk-gate/index.ts): live orders, brokerage APIs and credential access are denied before dispatch |
| Persistence | cron + memory | SKILL.md workflows 4/5: pre-market scans, weekend reviews, a thesis ledger |
| Multi-market | skill composition | US via aihf; A/H-shares via the `stock-technical-indicators` skill |

## Architecture

```
user (natural language)
   │
   ▼
deepseek-harness agent ── inject ──► skill/SKILL.md (this repo)
   │                                   │
   │   tools/pre-execute               ▼
   │ ◄── risk-gate plugin (denies      aihf CLI (ai-hedge-fund engine)
   │      live trading)                 │  stdout: CycleRecord / BacktestResult JSON
   │                                   ▼
   │                              records/*.json (persisted for review)
   │
   ├── cron: scheduled pre-market / weekend research workflows
   └── memory: thesis ledger, reviewed against records at expiry
```

The underlying engine [ai-hedge-fund](https://github.com/virattt/ai-hedge-fund) (MIT) makes the fund a declarative mandate: strategy pods, investor alpha models (Graham / Buffett / Munger / Lynch / Druckenmiller + a quant PEAD), risk limits and rebalance cadence are YAML data; tickers are a run-time `--tickers` input. aihf natively supports **DeepSeek as its reasoning LLM** — a DeepSeek model inside the DeepSeek harness driving an AI fund, one stack end to end.

## Quick start

```bash
# 1. Install the engine (isolated via pipx)
pipx install aihf

# 2. Configure keys (shell env, or ~/.hedge-fund/.env)
export FINANCIAL_DATASETS_API_KEY=...   # prices & fundamentals; free tier at financialdatasets.ai
export DEEPSEEK_API_KEY=...             # reasoning LLM for the alpha models

# 3. Verify the engine manually
aihf mandates/deep-value-weekly.yaml --tickers AAPL,MSFT,NVDA --backtest

# 4. Install the skill into dsh (add skill/ to your skills search path,
#    e.g. symlink into ~/.agents/skills/alpha-desk)
ln -s "$PWD/skill" ~/.agents/skills/alpha-desk

# 5. (Optional but recommended) enable the risk-gate plugin, see plugins/risk-gate/
```

Then talk to dsh in plain language:

- "Backtest the deep-value fund on AAPL, MSFT and NVDA over the past year"
- "Where do Buffett and Graham disagree on NVDA?"
- "Run the position signals every trading day before the open"
- "Review last week's watchlist — what was right, what was wrong?"

## Repository layout

```
dsh-alpha-desk/
├── skill/SKILL.md                        # the dsh skill (triggers, workflows, compliance red lines)
├── mandates/                             # three ready-to-run fund mandates
│   ├── deep-value-weekly.yaml            #   deep value (Graham×2 + Buffett + Munger), weekly
│   ├── fundamental-ls-market-neutral.yaml #  five-persona market-neutral L/S, monthly
│   └── inflections-daily.yaml            #   macro inflections (Druckenmiller + Lynch), daily
├── plugins/risk-gate/                    # dsh compliance hook plugin (tools/pre-execute)
├── records/                              # persisted run records (git-ignored)
└── LICENSE                               # MIT
```

## Compared with mainstream agent frameworks

| Capability | Alpha Desk (dsh) | Raw LangChain/CrewAI orchestration | Generic coding agent + prompts |
|---|---|---|---|
| Compliance boundary | Architectural: hook denies before tool dispatch | Roll your own executor wrapper | Prompt-only; model can bypass |
| Research engine | Mature open-source fund engine, reproducible JSON | Assemble yourself | Improvised by the model, not reproducible |
| Scheduled monitoring | dsh cron extension point, declarative | External scheduler needed | None |
| Thesis accountability | memory + persisted records, auto review at expiry | Build your own state layer | None |
| Hot reload / ecosystem | dsh plugin HMR; MCP/skill ecosystem reuse | — | — |

## Credits and boundaries

- Engine: [virattt/ai-hedge-fund](https://github.com/virattt/ai-hedge-fund) (MIT) — this project is an orchestration layer only and does not fork its code; its data source (Financial Datasets) mainly covers US equities
- Runtime: [deepseek-ai/deepseek-harness](https://github.com/deepseek-ai/deepseek-harness)
- A/H-share data is out of scope for the engine; backtests do not predict future returns; this project does not execute real trades for now
