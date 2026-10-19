// End-to-end: the real FastAPI server, real sockets, and the same store the
// React hook uses. backend/tests/e2e_server.py stands in for Auth0.
//
//   npm run test:e2e
//
// Needs the backend's Python environment. Set BACKEND_PYTHON if it isn't at
// backend/.venv/bin/python.

import { spawn } from 'node:child_process'
import { once } from 'node:events'
import { existsSync } from 'node:fs'
import { createInterface } from 'node:readline'
import { fileURLToPath } from 'node:url'
import { afterAll, beforeAll, describe, expect, it } from 'vitest'
import { livePhase } from '../src/live/liveReducer.js'
import { createLiveSession } from '../src/live/liveSession.js'

const backendDir = fileURLToPath(new URL('../../backend', import.meta.url))
const python = process.env.BACKEND_PYTHON || `${backendDir}/.venv/bin/python`

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

let server
let baseUrl
let tokens
const sessions = []

async function rest(person, method, path, body) {
  const res = await fetch(`${baseUrl}${path}`, {
    method,
    headers: {
      Authorization: `Bearer ${tokens[person]}`,
      ...(body ? { 'Content-Type': 'application/json' } : {}),
    },
    body: body ? JSON.stringify(body) : undefined,
  })
  const json = await res.json()
  if (!res.ok) throw new Error(`${method} ${path} -> ${res.status} ${JSON.stringify(json)}`)
  return json
}

function connect(person, sessionId) {
  const live = createLiveSession({
    sessionId,
    apiBaseUrl: baseUrl,
    getToken: async () => tokens[person],
  })
  live.start()
  sessions.push(live)
  return live
}

// Resolves once predicate(state) holds; fails with the last state otherwise.
function until(live, predicate, label, timeoutMs = 5000) {
  return new Promise((resolve, reject) => {
    const check = () => {
      if (!predicate(live.getState())) return false
      unsubscribe()
      clearTimeout(timer)
      resolve(live.getState())
      return true
    }
    const unsubscribe = live.subscribe(check)
    const timer = setTimeout(() => {
      unsubscribe()
      reject(new Error(`Timed out waiting for ${label}: ${JSON.stringify(live.getState())}`))
    }, timeoutMs)
    check()
  })
}

const phase = (name) => (state) => livePhase(state) === name
const choice = (state, correct) => state.currentQuestion.choices[correct ? 0 : 1].choice_id

async function newGame() {
  const quiz = await rest('host', 'POST', '/quizzes', QUIZ)
  return rest('host', 'POST', `/quizzes/${quiz.quiz_id}/sessions`)
}

beforeAll(async () => {
  if (!existsSync(python)) {
    throw new Error(`No backend Python at ${python}; set BACKEND_PYTHON.`)
  }
  server = spawn(python, ['-m', 'tests.e2e_server'], {
    cwd: backendDir,
    stdio: ['ignore', 'pipe', 'inherit'],
  })
  const [line] = await once(createInterface({ input: server.stdout }), 'line')
  ;({ base_url: baseUrl, tokens } = JSON.parse(line))
  for (let i = 0; i < 100; i += 1) {
    try {
      if ((await fetch(`${baseUrl}/health`)).ok) return
    } catch {
      // not listening yet
    }
    await new Promise((r) => setTimeout(r, 100))
  }
  throw new Error('e2e server did not start')
}, 30_000)

afterAll(() => {
  for (const live of sessions) live.close()
  server?.kill()
})

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
