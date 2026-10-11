import { atom, read, update } from 'claude-code'
import type { Register } from 'claude-code'

import type { Ledger, SessionSpend } from '../types'

// Each session's own cost ledger already sums every priced API response,
// subagents included; this mod keeps one row per session in $.store and
// totals them.
const PREFIX = 'session:'
const ledger = atom({ plugin: 'spend-tracker', key: 'ledger' } as const, null)


const money = (usd: number) => `$${usd.toFixed(usd >= 100 ? 2 : 4)}`

const sessions = async (keys: string[], get: (key: string) => Promise<unknown>) => {
  const rows: Array<SessionSpend & { id: string }> = []
  for (const key of keys) {
    if (!key.startsWith(PREFIX)) continue
    const row = (await get(key)) as SessionSpend | undefined
    if (row && typeof row.usd === 'number') {
      rows.push({ ...row, id: key.slice(PREFIX.length) })
    }
  }

  return rows
}

const total = (rows: SessionSpend[]) => rows.reduce((sum, row) => sum + row.usd, 0)

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    await $.command.register({
      name: 'spend',
      description: 'Total dollars spent on Claude across all sessions and agents',
      argumentHint: '[reset]',
    })
    const all = total(await sessions(await $.store.keys(), key => $.store.get(key)))
    if (all > 0) $.ui.status(`Claude spend: ${money(all)} all-time`)

    return next(e)
  })

  on('session.measure', async ($, e, next) => {
    const usd = e.cost?.usd
    if (usd === undefined || !e.changed.includes('cost')) return next(e)

    const id = await $.session.id()
    const key = PREFIX + id
    const saved = (await $.store.get(key)) as SessionSpend | undefined

    // A session seen for the first time in this process: when its ledger
    // starts below what was saved (a resume that restarted the count), the
    // saved figure becomes the base so nothing is lost or counted twice.
    const held = await update($, ledger, current =>
      current?.sessionId === id
        ? current
        : { sessionId: id, base: saved && usd < saved.usd ? saved.usd : 0 },
    )
    const row: SessionSpend = {
      usd: (held as Ledger).base + usd,
      updatedAt: await $.clock.now(),
      cwd: saved?.cwd ?? (await $.session.cwd()),
    }
    await $.store.set(key, row)

    const all = total(await sessions(await $.store.keys(), key => $.store.get(key)))
    $.ui.status(`Claude spend: ${money(row.usd)} this session · ${money(all)} all-time`)

    return next(e)
  })

  on('command.run', { command: 'spend' }, async ($, e) => {
    if ((e.args ?? '').trim() === 'reset') {
      for (const key of await $.store.keys()) {
        if (key.startsWith(PREFIX)) await $.store.delete(key)
      }
      await update($, ledger, () => null)
      $.ui.status(undefined)

      return { text: 'Claude spend history cleared.' }
    }

    const rows = await sessions(await $.store.keys(), key => $.store.get(key))
    const current = await read($, ledger)
    const mine = rows.find(row => row.id === current?.sessionId)
    const recent = [...rows].sort((a, b) => b.updatedAt - a.updatedAt).slice(0, 10)
    const lines = [
      `All-time Claude spend: ${money(total(rows))} across ${rows.length} session(s)`,
      `This session (incl. subagents): ${money(mine?.usd ?? 0)}`,
      '',
      'Most recent sessions:',
      ...recent.map(
        row =>
          `  ${money(row.usd).padStart(10)}  ${new Date(row.updatedAt).toISOString().slice(0, 16).replace('T', ' ')}  ${row.cwd ?? row.id}`,
      ),
    ]

    return { text: lines.join('\n') }
  })
}
