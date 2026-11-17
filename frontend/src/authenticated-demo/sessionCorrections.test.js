import { describe, expect, it } from 'vitest'

import {
  canCorrectSessionQuestion,
  canSelectCorrectChoice,
  correctionModesForChoice,
  correctionRequest,
} from './sessionCorrections'

describe('completed-session answer correction', () => {
  it('hides correction controls without backend permission', () => {
    const question = { session_question_id: 12 }

    expect(canCorrectSessionQuestion({ can_correct: false }, question)).toBe(false)
    expect(canCorrectSessionQuestion({ can_correct: true }, question)).toBe(true)
    expect(canCorrectSessionQuestion({ can_correct: true }, {})).toBe(false)
  })

  it('does not allow removing the final correct answer', () => {
    const onlyCorrect = { id: 4, correct: true }

    expect(
      canSelectCorrectChoice({
        editing: true,
        choice: onlyCorrect,
        currentChoices: [onlyCorrect],
        busy: false,
      }),
    ).toBe(false)
  })

  it('offers remove for an accepted answer and replace/add for another answer', () => {
    const current = [{ id: 4 }, { id: 5 }]

    expect(correctionModesForChoice(current, { id: 4 })).toEqual(['REMOVE'])
    expect(correctionModesForChoice(current, { id: 6 })).toEqual([
      'REPLACE',
      'ADD',
    ])
  })

  it.each(['REPLACE', 'ADD', 'REMOVE'])(
    'builds the %s request with the loaded score revision',
    (mode) => {
      expect(correctionRequest('8', mode, 3)).toEqual({
        choice_id: 8,
        mode,
        expected_score_revision: 3,
      })
    },
  )
})
