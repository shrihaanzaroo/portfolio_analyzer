import type { FsEntry } from 'claude-code'
import { expect, mock, test } from 'claude-code/testing'

import { addLine, costOfUsage, newTally } from './pricing'

const spend = (args = '') => ({
  command: 'spend',
  args,
  origin: { kind: 'composer' as const },
  presentation: { isFullscreen: false, columns: 80 },
})


const round4 = (usd: number | undefined) => (usd === undefined ? usd : Math.round(usd * 10000) / 10000)

const reply = (id: string, model: string, usage: object, extra: object = {}) =>
  JSON.stringify({
    type: 'assistant',
    requestId: `req_${id}`,
    cwd: '/work/app',
    timestamp: '2026-09-11T16:00:00.000Z',
    message: { id: `msg_${id}`, model, usage },
    ...extra,
  })

test('prices each token type at the model rate', () => {
  // 1M input at $4 + 1M 1h cache write at $8 + 1M cache read at $0.20 + 1M output at $20.
  const usd = costOfUsage('claude-opus-5-5', {
    input_tokens: 1_000_000,
    cache_creation_input_tokens: 1_000_000,
    cache_creation: { ephemeral_5m_input_tokens: 0, ephemeral_1h_input_tokens: 1_000_000 },
    cache_read_input_tokens: 1_000_000,
    output_tokens: 1_000_000,
  })
  expect(round4(usd)).toBe(32.2)
  expect(round4(costOfUsage('claude-fable-5-1', { cache_read_input_tokens: 4_000_000 }))).toBe(1)
  expect(round4(costOfUsage('claude-sonnet-5', { output_tokens: 100_000, speed: 'fast' }))).toBe(2)
  expect(costOfUsage('gpt-something', { output_tokens: 1 })).toBeUndefined()
})

test('counts a reply once however many blocks repeat it', () => {
  const tally = newTally()
  const line = reply('a', 'claude-sonnet-5', { output_tokens: 1_000_000 })
  addLine(tally, line)
  addLine(tally, line)
  addLine(tally, reply('b', 'claude-sonnet-5', {}, { costUSD: 0.5 }))
  addLine(tally, 'not json')
  expect(tally.replies).toBe(2)
  expect(round4(tally.usd)).toBe(10.5)
  expect(tally.cwd).toBe('/work/app')
})

test('/spend import adds past sessions and their subagents, once', async ($, on) => {
  mock.clock(on)
  mock.store(on, { 'session:live': { usd: 1, updatedAt: 1 } })
  const files: Record<string, string> = {
    '/home/me/.claude/projects/-work-app/old.jsonl': reply('1', 'claude-opus-5-5', { output_tokens: 100_000 }),
    '/home/me/.claude/projects/-work-app/old/subagents/agent-1.jsonl': reply('2', 'claude-sonnet-5', { output_tokens: 100_000 }),
    '/home/me/.claude/projects/-work-app/live.jsonl': reply('3', 'claude-opus-5-5', { output_tokens: 100_000 }),
    '/home/me/.claude/projects/-work-app/now.jsonl': reply('4', 'claude-opus-5-5', { output_tokens: 100_000 }),
  }
  const file = (name: string): FsEntry => ({ name, kind: 'file', size: 10, mtimeMs: 1, isLink: false })
  const dir = (name: string): FsEntry => ({ name, kind: 'dir', size: 0, mtimeMs: 0, isLink: false })
  const folders: Record<string, FsEntry[]> = {
    '/home/me/.claude/projects': [dir('-work-app')],
    '/home/me/.claude/projects/-work-app': [file('old.jsonl'), dir('old'), file('live.jsonl'), file('now.jsonl')],
    '/home/me/.claude/projects/-work-app/old': [dir('subagents')],
    '/home/me/.claude/projects/-work-app/old/subagents': [file('agent-1.jsonl')],
  }
  on('env.get', ($, e) => ({ value: e.name === 'HOME' ? '/home/me' : undefined }))
  on('fs.exists', ($, e) => ({ value: e.path in folders }))
  on('fs.list', ($, e) => ({ value: folders[e.path] ?? [] }))
  on('fs.read', ($, e) => ({ value: files[e.path] ?? '' }))
  on('session.id', () => ({ value: 'now' }))
  on('ui.status', () => ({ value: undefined }))
  on('command.run', () => ({ text: 'core' }))

  const first = await $.command.run(spend('import'))
  // old: $2 (Opus 5.5 output) + $1 (Sonnet 5 subagent); live and now are skipped.
  expect(first.text).toContain('Imported 1 past session(s), adding $3.0000')
  expect(first.text).toContain('2 session(s) were already counted')
  expect(first.text).toContain('All-time Claude spend is now $4.0000')

  const again = await $.command.run(spend('import'))
  expect(again.text).toContain('Imported 0 past session(s)')

  const report = await $.command.run(spend())
  expect(report.text).toContain('/work/app  (imported)')
})
