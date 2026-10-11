// API list prices per million tokens. Cache writes bill at 1.25x input for
// the 5-minute TTL and 2x for the 1-hour TTL. Longest prefix wins.
type Price = { input: number; output: number; cacheRead: number }

const PRICES: Array<[string, Price]> = [
  ['claude-fable-5-1', { input: 10, output: 50, cacheRead: 0.25 }],
  ['claude-mythos-5-1', { input: 10, output: 50, cacheRead: 0.25 }],
  ['claude-fable-5', { input: 10, output: 50, cacheRead: 1 }],
  ['claude-mythos-5', { input: 10, output: 50, cacheRead: 1 }],
  ['claude-opus-5-5', { input: 4, output: 20, cacheRead: 0.2 }],
  ['claude-opus-5', { input: 5, output: 25, cacheRead: 0.5 }],
  ['claude-opus-4-8', { input: 5, output: 25, cacheRead: 0.5 }],
  ['claude-opus-4-7', { input: 5, output: 25, cacheRead: 0.5 }],
  ['claude-opus-4-6', { input: 5, output: 25, cacheRead: 0.5 }],
  ['claude-opus-4-5', { input: 5, output: 25, cacheRead: 0.5 }],
  ['claude-opus-4', { input: 15, output: 75, cacheRead: 1.5 }],
  ['claude-sonnet-5-5', { input: 2, output: 10, cacheRead: 0.2 }],
  ['claude-sonnet-5', { input: 2, output: 10, cacheRead: 0.2 }],
  ['claude-sonnet-4', { input: 3, output: 15, cacheRead: 0.3 }],
  ['claude-3-7-sonnet', { input: 3, output: 15, cacheRead: 0.3 }],
  ['claude-3-5-sonnet', { input: 3, output: 15, cacheRead: 0.3 }],
  ['claude-haiku-5-5', { input: 0.1, output: 0.5, cacheRead: 0.01 }],
  ['claude-haiku-4-5', { input: 1, output: 5, cacheRead: 0.1 }],
  ['claude-3-5-haiku', { input: 0.8, output: 4, cacheRead: 0.08 }],
]

// Fast mode bills at twice the standard rate; web searches $10 per 1,000.
const FAST_MULTIPLIER = 2
const WEB_SEARCH_USD = 0.01

const priceOf = (model: string): Price | undefined => {
  const id = model.replace(/^(us\.|eu\.|global\.)?anthropic\./, '')
  let best: [string, Price] | undefined
  for (const entry of PRICES) {
    if (id.startsWith(entry[0]) && (!best || entry[0].length > best[0].length)) best = entry
  }

  return best?.[1]
}

type Usage = {
  input_tokens?: number
  output_tokens?: number
  cache_creation_input_tokens?: number
  cache_read_input_tokens?: number
  cache_creation?: { ephemeral_5m_input_tokens?: number; ephemeral_1h_input_tokens?: number }
  server_tool_use?: { web_search_requests?: number }
  speed?: string
}

export const costOfUsage = (model: string, usage: Usage): number | undefined => {
  let price = priceOf(model)
  if (!price) return undefined

  const input = usage.input_tokens ?? 0
  const cacheRead = usage.cache_read_input_tokens ?? 0
  const write1h = usage.cache_creation?.ephemeral_1h_input_tokens ?? 0
  const write5m = usage.cache_creation
    ? (usage.cache_creation.ephemeral_5m_input_tokens ?? 0)
    : (usage.cache_creation_input_tokens ?? 0)

  // Claude Haiku 5.5 prompts over 100K tokens bill at $0.50 / $2.50.
  if (model.includes('haiku-5-5') && input + cacheRead + write5m + write1h > 100_000) {
    price = { input: 0.5, output: 2.5, cacheRead: 0.05 }
  }

  const speed = usage.speed === 'fast' ? FAST_MULTIPLIER : 1
  const tokens =
    input * price.input +
    write5m * price.input * 1.25 +
    write1h * price.input * 2 +
    cacheRead * price.cacheRead +
    (usage.output_tokens ?? 0) * price.output

  return (tokens / 1_000_000) * speed + (usage.server_tool_use?.web_search_requests ?? 0) * WEB_SEARCH_USD
}

// What one transcript (or several, a session and its subagents) cost.
export type Tally = {
  usd: number
  replies: number
  unpriced: number
  seen: Record<string, true>
  cwd?: string
  lastAt?: number
}

export const newTally = (): Tally => ({ usd: 0, replies: 0, unpriced: 0, seen: {} })

// Adds one transcript line. A reply is written once per content block, each
// copy carrying the same usage, so replies are counted once by message id.
export const addLine = (tally: Tally, line: string): void => {
  if (!line.includes('"usage"') && !line.includes('"costUSD"')) return
  let row: {
    type?: string
    cwd?: string
    timestamp?: string
    requestId?: string
    costUSD?: number
    message?: { id?: string; model?: string; usage?: Usage }
  }
  try {
    row = JSON.parse(line)
  } catch {
    return
  }
  const usage = row.message?.usage
  if (row.type !== 'assistant' || (!usage && typeof row.costUSD !== 'number')) return

  const model = row.message?.model ?? ''
  if (model === '<synthetic>') return
  const id = `${row.message?.id ?? ''}:${row.requestId ?? ''}`
  if (id !== ':' && tally.seen[id]) return
  if (id !== ':') tally.seen[id] = true

  tally.cwd ??= row.cwd
  const at = row.timestamp ? Date.parse(row.timestamp) : NaN
  if (!Number.isNaN(at)) tally.lastAt = Math.max(tally.lastAt ?? 0, at)

  // Older Claude Code versions wrote each reply's cost beside it.
  const usd = typeof row.costUSD === 'number' ? row.costUSD : usage ? costOfUsage(model, usage) : undefined
  if (usd === undefined) {
    tally.unpriced += 1

    return
  }
  tally.usd += usd
  tally.replies += 1
}
