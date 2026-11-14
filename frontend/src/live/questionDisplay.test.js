import { describe, expect, it } from 'vitest'
import {
  ANSWER_SUITS,
  PREVIEW_MS,
  answerSuit,
  inPreview,
  previewEndsAt,
} from './questionDisplay.js'

const opened = Date.parse('2026-11-14T15:00:00Z')

function question(seconds) {
  return {
    opened_at: new Date(opened).toISOString(),
    closes_at: new Date(opened + seconds * 1000).toISOString(),
  }
}

describe('answerSuit', () => {
  it('gives each of the first four positions its own suit', () => {
    expect([0, 1, 2, 3].map(answerSuit)).toEqual(['spade', 'heart', 'diamond', 'club'])
    expect(new Set(ANSWER_SUITS).size).toBe(4)
  })

  it('repeats the suits after four positions, like the answer colours', () => {
    expect(answerSuit(4)).toBe('spade')
    expect(answerSuit(7)).toBe('club')
  })

  it('falls back to the first suit for a bad index', () => {
    expect(answerSuit(-1)).toBe('spade')
    expect(answerSuit(undefined)).toBe('spade')
  })
})

describe('question preview', () => {
  it('lasts PREVIEW_MS from when the question opened', () => {
    expect(previewEndsAt(question(30), opened)).toBe(opened + PREVIEW_MS)
    expect(inPreview(question(30), opened, opened + PREVIEW_MS - 1)).toBe(true)
    expect(inPreview(question(30), opened, opened + PREVIEW_MS)).toBe(false)
  })

  it('uses at most a quarter of a short time limit', () => {
    expect(previewEndsAt(question(5), opened)).toBe(opened + 1250)
  })

  it('is capped from when the screen saw the question if the local clock is behind', () => {
    // Local clock 10 s behind: the question looks like it opens in the future.
    const seenAt = opened - 10_000
    expect(previewEndsAt(question(30), seenAt)).toBe(seenAt + PREVIEW_MS)
  })

  it('is skipped for a question that opened earlier (a reconnect)', () => {
    const seenAt = opened + 12_000
    expect(inPreview(question(30), seenAt, seenAt)).toBe(false)
  })

  it('is skipped when the question has no usable timing', () => {
    expect(previewEndsAt({}, opened)).toBeNull()
    expect(previewEndsAt(null, opened)).toBeNull()
    expect(inPreview({ opened_at: 'x', closes_at: 'y' }, opened, opened)).toBe(false)
  })
})
