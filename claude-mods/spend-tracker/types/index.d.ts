export type Ledger = { sessionId: string; base: number }

export type SessionSpend = { usd: number; updatedAt: number; cwd?: string; imported?: boolean }

declare module 'claude-code' {
  interface PluginState {
    'spend-tracker': { ledger: Ledger | null }
  }
}
