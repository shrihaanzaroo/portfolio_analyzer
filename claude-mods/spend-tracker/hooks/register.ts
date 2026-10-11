import { atom, read, update } from 'claude-code'
import type { Register } from 'claude-code'

import type { Ledger, SessionSpend } from '../types'
import { addLine, newTally } from './pricing'
import type { Tally } from './pricing'

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

// $.fs.read stops at 4 MiB; larger transcripts are streamed through grep
// (or `type` on Windows) instead.
const READ_LIMIT = 4 * 1024 * 1024

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    await $.command.register({
      name: 'spend',
      description: 'Total dollars spent on Claude across all sessions and agents',
      argumentHint: '[import|reset]',
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
    const arg = (e.args ?? '').trim()

    if (arg === 'import') {
      const home = (await $.env.get('CLAUDE_CONFIG_DIR')) ??
        `${(await $.env.get('HOME')) ?? (await $.env.get('USERPROFILE')) ?? ''}/.claude`
      const isWindows = (await $.env.get('OS')) === 'Windows_NT'
      const projects = `${home}/projects`
      if (!(await $.fs.exists(projects))) {
        return { text: `No saved Claude Code sessions found in ${projects}.` }
      }

      // The running session is tracked live; importing it too would count it twice.
      const known = new Set([...(await $.store.keys()), PREFIX + (await $.session.id())])
      let imported = 0
      let skipped = 0
      let unreadable = 0
      let unpriced = 0
      let added = 0

      const readInto = async (tally: Tally, path: string, size: number) => {
        if (size <= READ_LIMIT) {
          for (const line of (await $.fs.read(path)).split('\n')) addLine(tally, line)

          return
        }
        const argv = isWindows ? ['cmd', '/c', 'type', path.replaceAll('/', '\\')] : ['grep', '-F', '"usage"', path]
        let rest = ''
        for await (const { stream, text } of $.process.spawn({ argv })) {
          if (stream !== 'stdout') continue
          const lines = (rest + text).split('\n')
          rest = lines.pop() ?? ''
          for (const line of lines) addLine(tally, line)
        }
        addLine(tally, rest)
      }

      // A session's subagents are saved under a folder named for the session.
      const readFolder = async (tally: Tally, folder: string, depth: number): Promise<void> => {
        for (const entry of await $.fs.list(folder)) {
          const path = `${folder}/${entry.name}`
          if (entry.kind === 'dir' && depth < 3) await readFolder(tally, path, depth + 1)
          if (entry.kind === 'file' && entry.name.endsWith('.jsonl')) await readInto(tally, path, entry.size)
        }
      }

      for (const project of await $.fs.list(projects)) {
        if (project.kind !== 'dir') continue
        const dir = `${projects}/${project.name}`
        const entries = await $.fs.list(dir)
        for (const file of entries) {
          if (file.kind !== 'file' || !file.name.endsWith('.jsonl')) continue
          const id = file.name.slice(0, -'.jsonl'.length)
          if (known.has(PREFIX + id)) {
            skipped += 1
            continue
          }
          $.ui.status(`Claude spend: importing ${imported + skipped + unreadable + 1}…`)

          const tally = newTally()
          try {
            await readInto(tally, `${dir}/${file.name}`, file.size)
            if (entries.some(other => other.kind === 'dir' && other.name === id)) {
              await readFolder(tally, `${dir}/${id}`, 0)
            }
          } catch {
            unreadable += 1
            continue
          }
          unpriced += tally.unpriced
          if (tally.replies === 0) continue

          const row: SessionSpend = {
            usd: tally.usd,
            updatedAt: tally.lastAt ?? file.mtimeMs,
            cwd: tally.cwd,
            imported: true,
          }
          await $.store.set(PREFIX + id, row)
          imported += 1
          added += tally.usd
        }
      }

      const all = total(await sessions(await $.store.keys(), key => $.store.get(key)))
      $.ui.status(`Claude spend: ${money(all)} all-time`)
      const notes = [
        `Imported ${imported} past session(s), adding ${money(added)} at API list prices.`,
        skipped > 0 ? `${skipped} session(s) were already counted and left as they were.` : '',
        unreadable > 0 ? `${unreadable} file(s) could not be read.` : '',
        unpriced > 0 ? `${unpriced} ${unpriced === 1 ? 'reply' : 'replies'} used a model with no known price and were left out.` : '',
        `All-time Claude spend is now ${money(all)}.`,
      ]

      return { text: notes.filter(Boolean).join('\n') }
    }

    if (arg === 'reset') {
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
      rows.some(row => row.imported) ? '' : 'Run /spend import to add sessions from before the tracker was installed.',
      '',
      'Most recent sessions:',
      ...recent.map(
        row =>
          `  ${money(row.usd).padStart(10)}  ${new Date(row.updatedAt).toISOString().slice(0, 16).replace('T', ' ')}  ${row.cwd ?? row.id}${row.imported ? '  (imported)' : ''}`,
      ),
    ]

    return { text: lines.join('\n') }
  })
}
