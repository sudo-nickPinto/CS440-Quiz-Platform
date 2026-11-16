import { describe, expect, it } from 'vitest'

import { ANSWER_STEPS, QUESTION_STEPS, fitSteps } from './fitText'

// A fake page. `questionFits(size)` and `answersFit(qSize, aSize)` say
// whether text at those pixel sizes fits.
function run({ questionFits = () => true, answersFit = () => true, answerSteps = ANSWER_STEPS }) {
  const applied = []
  let q = 0
  let a = 0
  const result = fitSteps({
    questionSteps: QUESTION_STEPS,
    answerSteps,
    apply(nextQ, nextA) {
      q = nextQ
      a = nextA
      applied.push([QUESTION_STEPS[q], answerSteps[a]])
    },
    measure: () => ({
      question: !questionFits(QUESTION_STEPS[q]),
      answers: answerSteps.length > 0 && !answersFit(QUESTION_STEPS[q], answerSteps[a]),
    }),
  })
  return { result, applied, sizes: applied.at(-1) }
}

describe('fitSteps', () => {
  it('keeps the biggest sizes when everything fits', () => {
    const { result, applied } = run({})
    expect(result).toEqual({ q: 0, a: 0, fits: true })
    expect(applied).toEqual([[80, 34]])
  })

  it('shrinks only the question while the question overflows', () => {
    const { sizes } = run({ questionFits: (q) => q <= 56 })
    expect(sizes).toEqual([56, 34])
  })

  it('keeps the question about 1.8 times the answers while shrinking both', () => {
    // Fits once the two sizes add up to 70px or less.
    const { sizes, result } = run({ answersFit: (q, a) => q + a <= 70 })
    expect(result.fits).toBe(true)
    expect(sizes).toEqual([42, 24])
  })

  it('keeps shrinking the answers once the question is at its smallest', () => {
    const { sizes } = run({ questionFits: (q) => q <= 28, answersFit: (q, a) => a <= 22 })
    expect(sizes).toEqual([28, 22])
  })

  it('reports overflow when even the smallest steps do not fit', () => {
    const { result, sizes } = run({ answersFit: () => false })
    expect(result.fits).toBe(false)
    expect(sizes).toEqual([28, 22])
  })

  it('works with no answers (the question preview)', () => {
    const { sizes, result } = run({ questionFits: (q) => q <= 48, answerSteps: [] })
    expect(result.fits).toBe(true)
    expect(sizes[0]).toBe(48)
  })
})
