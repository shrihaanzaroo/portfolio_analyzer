import { expect, mock, test } from 'claude-code/testing'

const spend = (args = '') => ({
  command: 'spend',
  args,
  origin: { kind: 'composer' as const },
  presentation: { isFullscreen: false, columns: 80 },
})


const context = { window: 200000 }

test('totals spend across sessions and survives a restarted ledger', async ($, on) => {
  mock.clock(on, { now: 1_700_000_000_000 })
  mock.store(on, { 'session:old': { usd: 5, updatedAt: 1, cwd: '/old' } })
  let sessionId = 'a'
  const statuses: Array<string | undefined> = []
  on('session.id', () => ({ value: sessionId }))
  on('session.cwd', () => ({ value: '/repo' }))
  on('ui.status', ($, e) => {
    statuses.push(e.text)
    return { value: undefined }
  })
  on('session.measure', ($, e) => ({ changed: e.changed }))
  on('command.register', ($, e) => ({ value: { command: e.name } }))
  on('command.run', () => ({ text: 'core' }))

  const measure = (usd: number) =>
    $.session.measure({ context, rateLimits: [], cost: { usd }, changed: ['cost'] })

  await measure(1.25)
  expect(statuses.at(-1)).toBe('spend $1.25 · $6.25 total')

  await measure(2)
  expect(statuses.at(-1)).toBe('spend $2.00 · $7.00 total')

  // A /clear: a new session id, its ledger from zero.
  sessionId = 'b'
  await measure(0.5)
  expect(statuses.at(-1)).toBe('spend $0.50 · $7.50 total')

  const report = await $.command.run(spend())
  expect(report.text).toContain('All-time Claude spend: $7.50 across 3 session(s)')
  expect(report.text).toContain('This session (incl. subagents): $0.50')

  const cleared = await $.command.run(spend('reset'))
  expect(cleared.text).toBe('Claude spend history cleared.')
  const empty = await $.command.run(spend())
  expect(empty.text).toContain('$0.00 across 0 session(s)')
})

test('a resumed session whose ledger restarted keeps what it had', async ($, on) => {
  mock.clock(on)
  mock.store(on, { 'session:r': { usd: 3, updatedAt: 1 } })
  const statuses: Array<string | undefined> = []
  on('session.id', () => ({ value: 'r' }))
  on('session.cwd', () => ({ value: '/repo' }))
  on('ui.status', ($, e) => {
    statuses.push(e.text)
    return { value: undefined }
  })
  on('session.measure', ($, e) => ({ changed: e.changed }))

  await $.session.measure({ context, rateLimits: [], cost: { usd: 0.1 }, changed: ['cost'] })
  expect(statuses.at(-1)).toBe('spend $3.10 · $3.10 total')
})
