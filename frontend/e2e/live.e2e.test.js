// End-to-end: the real FastAPI server, real sockets, and the same store the
// React hook uses. backend/tests/e2e_server.py stands in for Auth0.
//
//   npm run test:e2e
//
// Server and helpers: e2e/harness.js.

import { describe, expect, it } from 'vitest'
import { connect, phase, rest, runE2EServer, until } from './harness.js'

runE2EServer()

const QUIZ = {
  title: 'E2E Live Quiz',
  questions: [1, 2, 3].map((n) => ({
    question_text: `Question ${n}?`,
    time_limit_seconds: 30,
    choices: [
      { choice_text: 'Right', is_correct: true },
      { choice_text: 'Wrong', is_correct: false },
    ],
  })),
}

const choice = (state, correct) => state.currentQuestion.choices[correct ? 0 : 1].choice_id

// Every session belongs to a class and needs an approved quiz version:
// faculty host makes a class, alice and bob join it by code, and the host
// creates, publishes, submits and approves the quiz before hosting it there.
async function newGame() {
  await rest('host', 'GET', '/me')
  await rest('host', 'POST', '/e2e/faculty/host')
  const course = await rest('host', 'POST', '/classes', { name: 'E2E class' })
  for (const person of ['alice', 'bob']) {
    await rest(person, 'POST', '/classes/join', { code: course.join_code })
  }
  const base = `/classes/${course.class_id}`
  const draft = await rest('host', 'POST', `${base}/quizzes`, QUIZ)
  const quiz = await rest('host', 'POST', `${base}/quizzes/${draft.quiz_id}/publish`, {
    expected_revision: draft.revision,
  })
  const submission = await rest('host', 'POST', `${base}/quiz-submissions`, {
    quiz_version_id: quiz.version.quiz_version_id,
  })
  await rest('host', 'PATCH', `${base}/quiz-submissions/${submission.submission_id}`, {
    status: 'APPROVED',
  })
  return rest('host', 'POST', `${base}/quizzes/${quiz.quiz_id}/sessions`)
}

describe('live session over a real socket', () => {
  it('runs the demo: join, skip, answer, end, final leaderboard', async () => {
    const game = await newGame()
    const sid = game.session_id

    const host = connect('host', sid)
    await until(host, phase('lobby'), 'host lobby')
    expect(host.getState().role).toBe('host')
    expect(host.getState().session.join_code).toBe(game.join_code)

    for (const person of ['alice', 'bob']) {
      await rest(person, 'POST', '/sessions/join', { join_code: game.join_code })
    }
    await until(host, (s) => s.participants.length === 2, 'two joins')
    expect(host.getState().participants.map((p) => p.display_name).sort()).toEqual(['Alice', 'Bob'])

    const alice = connect('alice', sid)
    const bob = connect('bob', sid)
    await until(alice, phase('lobby'), 'alice lobby')
    await until(bob, phase('lobby'), 'bob lobby')
    const everyone = [host, alice, bob]

    // Q1: skipped by the host before anyone answers.
    await host.openNextQuestion()
    await Promise.all(everyone.map((live) => until(live, phase('question'), 'Q1 open')))
    await host.skip()
    for (const live of everyone) {
      const state = await until(live, (s) => s.lastResults !== null, 'Q1 results')
      expect(state.lastClosed.reason).toBe('HOST')
    }
    expect(alice.getState().lastResults.me.points_awarded).toBe(0)

    // Q2: both answer, so it closes by itself.
    await host.openNextQuestion()
    await until(alice, phase('question'), 'alice Q2')
    await until(bob, phase('question'), 'bob Q2')
    await alice.submitAnswer(choice(alice.getState(), true))
    expect(alice.getState().myAnswer).not.toBeNull()
    await bob.submitAnswer(choice(bob.getState(), false))
    for (const live of everyone) {
      const state = await until(
        live,
        (s) => s.lastResults?.session_question_id === s.lastQuestion?.session_question_id && s.lastQuestion?.question_order === 2,
        'Q2 results',
      )
      expect(state.lastClosed.reason).toBe('ALL_ANSWERED')
    }
    expect(alice.getState().lastResults.me).toMatchObject({ is_correct: true, rank: 1 })
    expect(bob.getState().lastResults.me).toMatchObject({ is_correct: false, rank: 2 })
    expect(host.getState().lastResults.participants).toHaveLength(2)

    // Q3: Alice answers, then the host ends the game with it still open.
    await host.openNextQuestion()
    await until(alice, phase('question'), 'alice Q3')
    await alice.submitAnswer(choice(alice.getState(), true))
    await host.end()

    const finals = await Promise.all(everyone.map((live) => until(live, (s) => s.final && s.connection === 'ended', 'ended + closed')))
    for (const state of finals) {
      expect(state.final.reason).toBe('COMPLETED')
      expect(state.connection).toBe('ended')
      expect(state.lastClosed.reason).toBe('HOST') // Q3 closed by the end
    }
    const [hostFinal, aliceFinal, bobFinal] = finals
    expect(hostFinal.final.standings.map((r) => [r.display_name, r.correct_count, r.final_rank])).toEqual([
      ['Alice', 2, 1],
      ['Bob', 0, 2],
    ])
    expect(aliceFinal.final.me).toMatchObject({ display_name: 'Alice', final_rank: 1 })
    expect(bobFinal.final.me).toMatchObject({ display_name: 'Bob', final_rank: 2 })
    expect(bobFinal.final.leaderboard.map((r) => r.display_name)).toEqual(['Alice', 'Bob'])

    // A reload after the end gets 4410 and loads the stored results.
    const reloaded = connect('bob', sid)
    const restored = await until(reloaded, (s) => s.final !== null, 'results after 4410')
    expect(restored.connection).toBe('ended')
    expect(restored.final).toMatchObject({ status: 'COMPLETED', me: { final_rank: 2 } })
  })

  it('handles a participant leaving and the host cancelling in the lobby', async () => {
    const game = await newGame()
    const sid = game.session_id
    const host = connect('host', sid)
    await until(host, phase('lobby'), 'host lobby')
    await rest('alice', 'POST', '/sessions/join', { join_code: game.join_code })
    await rest('bob', 'POST', '/sessions/join', { join_code: game.join_code })
    await until(host, (s) => s.participants.length === 2, 'two joins')

    const alice = connect('alice', sid)
    const bob = connect('bob', sid)
    await until(alice, phase('lobby'), 'alice lobby')
    await until(bob, phase('lobby'), 'bob lobby')

    // A participant can't use host controls; the error keeps the socket.
    await expect(bob.cancel()).rejects.toMatchObject({ code: 'session_host_denied' })
    expect(bob.getState().lastError.code).toBe('session_host_denied')

    await alice.leave()
    await until(alice, phase('left'), 'alice left')
    const afterLeave = await until(host, (s) => s.participantCount === 1, 'host sees leave')
    expect(afterLeave.participants.map((p) => p.display_name)).toEqual(['Bob'])

    await host.cancel()
    for (const live of [host, bob]) {
      const state = await until(live, phase('ended'), 'cancelled')
      expect(state.final.reason).toBe('CANCELLED')
    }
  })
})
