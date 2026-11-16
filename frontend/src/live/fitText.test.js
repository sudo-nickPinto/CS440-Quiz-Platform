import { describe, expect, it } from 'vitest'

import { fitSteps } from './fitText'

// A fake page: the question fits at step `qFits` or smaller, the answers at
// step `aFits` or smaller (relative to how far the question has shrunk).
function run({ qFits, aFits, qSteps = 7, aSteps = 6 }) {
  const applied = []
  let q = 0
  let a = 0
  const result = fitSteps({
    questionSteps: Array.from({ length: qSteps }, (_, i) => i),
    answerSteps: Array.from({ length: aSteps }, (_, i) => i),
    apply(nextQ, nextA) {
      q = nextQ
      a = nextA
      applied.push([q, a])
    },
    measure: () => ({ question: q < qFits, answers: q + a < aFits }),
  })
  return { result, applied }
}

describe('fitSteps', () => {
  it('keeps the biggest sizes when everything fits', () => {
    const { result, applied } = run({ qFits: 0, aFits: 0 })
    expect(result).toEqual({ q: 0, a: 0, fits: true })
    expect(applied).toEqual([[0, 0]])
  })

  it('shrinks only the question while the question overflows', () => {
    const { result } = run({ qFits: 3, aFits: 0 })
    expect(result).toEqual({ q: 3, a: 0, fits: true })
  })

  it('takes turns, question first, when the answers overflow', () => {
    const { applied, result } = run({ qFits: 0, aFits: 4 })
    expect(applied).toEqual([
      [0, 0],
      [1, 0],
      [1, 1],
      [2, 1],
      [2, 2],
    ])
    expect(result.fits).toBe(true)
  })

  it('keeps shrinking the other one once one reaches its smallest step', () => {
    const { result } = run({ qFits: 0, aFits: 6, qSteps: 2, aSteps: 6 })
    expect(result).toEqual({ q: 1, a: 5, fits: true })
  })

  it('reports overflow when even the smallest steps do not fit', () => {
    const { result } = run({ qFits: 0, aFits: 99, qSteps: 3, aSteps: 3 })
    expect(result).toEqual({ q: 2, a: 2, fits: false })
  })

  it('works with no answers (the question preview)', () => {
    const { result } = run({ qFits: 2, aFits: 0, aSteps: 0 })
    expect(result).toEqual({ q: 2, a: 0, fits: true })
  })
})
