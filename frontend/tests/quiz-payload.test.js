import assert from 'node:assert/strict'
import test from 'node:test'
import { toQuizCreate } from '../src/authenticated-demo/quizPayload.js'

function editor() {
  return {
    title: '  Geography  ',
    defaultTime: '20',
    questions: [{
      id: 'browser-only-id',
      text: '  Capital of France?  ',
      options: [' Paris ', 'Rome'],
      correct: 0,
      limit: null,
    }],
  }
}

test('maps editor state to the exact backend request shape', () => {
  assert.deepEqual(toQuizCreate(editor()), {
    title: 'Geography',
    questions: [{
      question_text: 'Capital of France?',
      time_limit_seconds: 20,
      base_points: 1000,
      choices: [
        { choice_text: 'Paris', is_correct: true },
        { choice_text: 'Rome', is_correct: false },
      ],
    }],
  })
})

test('uses a per-question time override', () => {
  const value = editor()
  value.questions[0].limit = '45'

  assert.equal(
    toQuizCreate(value).questions[0].time_limit_seconds,
    45,
  )
})

test('rejects missing correct answer', () => {
  const value = editor()
  value.questions[0].correct = null

  assert.throws(
    () => toQuizCreate(value),
    /select the correct answer/,
  )
})

test('rejects invalid timers instead of sending NaN or zero', () => {
  for (const limit of ['', 'invalid', '4', '301', '5.5']) {
    const value = editor()
    value.questions[0].limit = limit

    assert.throws(
      () => toQuizCreate(value),
      /whole number/,
    )
  }
})

test('rejects blank choices and more than four choices', () => {
  const value = editor()
  value.questions[0].options[0] = '   '

  assert.throws(
    () => toQuizCreate(value),
    /choices must/,
  )

  value.questions[0].options = ['A', 'B', 'C', 'D', 'E']

  assert.throws(
    () => toQuizCreate(value),
    /two to four/,
  )
})

test('rejects an empty quiz', () => {
  assert.throws(
    () => toQuizCreate({ ...editor(), questions: [] }),
    /at least one/,
  )
})
