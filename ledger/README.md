# 公开预测台账

每个预测是一条**先于结果**入库的结构化观点；到期日用真实收盘价**机械结算**，无人工裁量。
这是本工作台"观点要被记录、被检验、被追责"的落点，也是对外可验证的战绩凭证。

## 文件布局

```
ledger/
├── predictions/YYYYMMDD-<symbol>-<direction>.json   # 预测（status: open/settled/void）
├── settlements/<同id>.json                          # 结算记录（收盘价、区间收益、hit/miss）
└── stats.md                                         # 战绩汇总（report --write 自动生成）
```

## 预测字段

| 字段 | 说明 |
|---|---|
| `asset.symbol / market / name` | 标的；market ∈ `cn` / `hk` / `us` |
| `direction` | `long` / `short` / `neutral`（区间横盘） |
| `confidence` | (0, 1]，agent 自评置信度，用于事后校准 |
| `as_of` | 基线日 |
| `horizon_end` | 到期日（必须晚于基线日） |
| `deadband` | 死区，默认 ±0.5%，过滤噪音 |
| `rationale` | 理由，**必填**——没有理由的观点不入台账 |
| `invalidate_if` | 失效条件（定性，仅供复盘参考，不参与结算） |
| `source` | 产生观点的工作流 / mandate |

## 结算规则（机械，无裁量）

- 基线价 = `as_of` 当日或之后**首个交易日**收盘价
- 终值价 = `horizon_end` 当日或之前**最近交易日**收盘价
- 区间收益 `ret = 终值 / 基线 - 1`
- `long`：`ret > +deadband` 判 hit；`short`：`ret < -deadband` 判 hit；`neutral`：`|ret| ≤ deadband` 判 hit；其余 miss
- 行情数据缺失 → 结算记 `void`，不计入胜率

数据源：腾讯 gtimg 日K（A股前复权；港股/美股原始价，美股代码自动尝试 `.OQ`/`.N` 后缀），免费无 key。

## 防篡改边界（诚实声明）

预测文件在给出瞬间由 `tools/ledger.py new` 落盘并 `git commit`，结算后再次 commit——
预测先于结果进入 git 历史，commit 序列就是时间戳证据。但要说明：

- 本机 commit 时间理论上可改，**尽早 push 到 GitHub** 才构成公开可查的时间证据；
- 历史不改写（只追加）是纪律约定，强 force-push 会破坏全部可信度，等价于自毁凭证。

台账自 **2026-09-23** 起运行，初始为空——战绩只能来自真实结算累积，不接受任何回填。
这也是设计的一部分：一条从零开始、过程全公开的记录，比任何无法审计的"历史胜率"都值钱。

## 常用命令

```bash
python3 tools/ledger.py new --symbol 600519 --market cn --direction long \
  --confidence 0.6 --horizon 2026-10-23 --rationale "……"

python3 tools/ledger.py settle              # 结算所有到期预测
python3 tools/ledger.py settle --force      # 含未到期但数据已齐的（历史演练）
python3 tools/ledger.py report --write      # 重新生成 stats.md
python3 tools/ledger.py verify --symbol 600519 --market cn   # 行情通路自检
```

演练不影响正式台账：`LEDGER_DIR=/tmp/xxx python3 tools/ledger.py …`
