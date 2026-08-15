/**
 * risk-gate — Alpha Desk 的合规门禁。
 *
 * 挂在 `tools/pre-execute` 上：任何指向真实券商、真实下单、凭证改写的
 * 工具调用在这里被单调拒绝，不进入分发。投研（只读数据、回测、报告）
 * 一律放行。
 *
 * 这是 dsh 微内核的标准用法：策略层不修改执行循环本身，
 * 只在 waterfall 扩展点上返回类型化决策。
 *
 * 本文件是 index.ts 的编译产物（去掉 `import type` 与返回类型标注），
 * 因为 Node 的 type-stripping 不适用于 node_modules 内的 .ts 文件；
 * runtime 入口见 package.json 的 `main`。
 */

export const name = 'alpha-desk-risk-gate'

/** 命中即拒绝的命令片段（小写匹配）。只列实盘/凭证类，不误伤投研。 */
const DENY_PATTERNS = [
  // 海外券商 CLI / API
  { pattern: /\bibkr?\b/, label: 'Interactive Brokers' },
  { pattern: /\balpaca\b/, label: 'Alpaca' },
  { pattern: /\btda(meritrade)?\b/, label: 'TD Ameritrade' },
  { pattern: /\bschwab\b/, label: 'Charles Schwab' },
  { pattern: /\bwebull\b/, label: 'Webull' },
  // 港美股互联网券商
  { pattern: /富途|futu|moomoo/, label: 'Futu/moomoo' },
  { pattern: /老虎|tiger\s*trade/, label: 'Tiger Brokers' },
  // 通用下单动词 + 券商域名写请求
  { pattern: /place[_-]?order|submit[_-]?order|market[_-]?order/, label: 'order placement' },
  { pattern: /curl[^\n]*\b(api\.(alpaca|ibkr|webull)|openapi\.futunn)/, label: 'brokerage API write' },
  // 凭证文件改写（读也拒绝，.env 里装着数据/LLM key）
  { pattern: /\.hedge-fund\/\.env/, label: 'credential file' },
  // aihf 未来若长出实盘开关，一律按死
  { pattern: /--live\b|--paper-trade\s*=?\s*off/, label: 'live trading flag' },
]

/** 从工具调用里抠出可检查的文本（bash 命令、文件路径、URL 等）。 */
function inspectableText(exec) {
  try {
    return JSON.stringify(exec.input ?? exec).toLowerCase()
  } catch {
    return String(exec).toLowerCase()
  }
}

export function apply(ctx) {
  ctx.on('tools/pre-execute', async (exec, next) => {
    const text = inspectableText(exec)
    for (const { pattern, label } of DENY_PATTERNS) {
      if (pattern.test(text)) {
        return {
          kind: 'deny',
          reason:
            `risk-gate: blocked ${label}. Alpha Desk 是纯投研环境，禁止实盘交易与凭证访问。` +
            ` (This workspace is research-only: live trading and credential access are denied by policy.)`,
        }
      }
    }
    return next()
  })
}
