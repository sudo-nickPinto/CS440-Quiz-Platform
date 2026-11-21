#!/usr/bin/env node
// Live quiz load test: one class running a real live session with many
// students, through the real FastAPI app and the same live-session store the
// React app uses. Prints how long each step takes for everyone.
//
//   npm run loadtest                          # 50 students, 5 questions
//   npm run loadtest -- --students 150 --questions 10
//
// It starts backend/tests/e2e_server.py itself (a test key stands in for
// Auth0, data goes to a throwaway SQLite file). Set E2E_DATABASE_URL to a
// migrated MySQL test database to run against MySQL instead, which is closer
// to the deployed app. See loadtest/README.md.

import { spawn } from 'node:child_process'
import { once } from 'node:events'
import { existsSync } from 'node:fs'
import { createInterface } from 'node:readline'
import { fileURLToPath } from 'node:url'
import { parseArgs } from 'node:util'
import { livePhase } from '../src/live/liveReducer.js'
import { createLiveSession } from '../src/live/liveSession.js'

const { values: args } = parseArgs({
  options: {
    students: { type: 'string', default: '50' },
    questions: { type: 'string', default: '5' },
    timeout: { type: 'string', default: '30' },
  },
})
const STUDENTS = Number(args.students)
const QUESTIONS = Number(args.questions)
const TIMEOUT_MS = Number(args.timeout) * 1000
if (!(STUDENTS >= 1 && STUDENTS <= 2000) || !(QUESTIONS >= 1 && QUESTIONS <= 50)) {
  console.error('Use --students 1-2000 and --questions 1-50.')
  process.exit(2)
}

const backendDir = fileURLToPath(new URL('../../backend', import.meta.url))
const python = process.env.BACKEND_PYTHON || `${backendDir}/.venv/bin/python`
const server = { baseUrl: null, tokens: null }
const students = Array.from({ length: STUDENTS }, (_, i) => `student${String(i + 1).padStart(3, '0')}`)

// -- measuring -------------------------------------------------------------

const timings = new Map() // step -> milliseconds[]
const failures = new Map() // step -> count
const firstError = new Map() // step -> message
const record = (step, ms) => (timings.get(step) ?? timings.set(step, []).get(step)).push(ms)
const fail = (step, error) => {
  failures.set(step, (failures.get(step) ?? 0) + 1)
  if (!firstError.has(step)) firstError.set(step, String(error?.message ?? error).slice(0, 200))
}

// Runs fn for every student at once; times each, and keeps going past failures.
async function everyone(step, people, fn) {
  const ok = []
  await Promise.all(
    people.map(async (person) => {
      const start = performance.now()
      try {
        await fn(person)
        record(step, performance.now() - start)
        ok.push(person)
      } catch (error) {
        fail(step, error)
      }
    }),
  )
  return people.filter((person) => ok.includes(person))
}

// Like everyone(), but each time is measured from `since` (a moment shared by
// all students, such as the host's command) to when fn finishes.
async function everyoneSince(step, people, since, fn) {
  const ok = []
  await Promise.all(
    people.map(async (person) => {
      try {
        await fn(person)
        record(step, performance.now() - since)
        ok.push(person)
      } catch (error) {
        fail(step, error)
      }
    }),
  )
  return people.filter((person) => ok.includes(person))
}

const pct = (sorted, p) => sorted[Math.min(sorted.length - 1, Math.ceil((p / 100) * sorted.length) - 1)]

// -- server and requests ---------------------------------------------------

async function startServer() {
  if (!existsSync(python)) throw new Error(`No backend Python at ${python}; set BACKEND_PYTHON.`)
  const child = spawn(python, ['-m', 'tests.e2e_server'], {
    cwd: backendDir,
    stdio: ['ignore', 'pipe', 'inherit'],
    env: { ...process.env, E2E_EXTRA_PEOPLE: String(STUDENTS) },
  })
  const [line] = await once(createInterface({ input: child.stdout }), 'line')
  ;({ base_url: server.baseUrl, tokens: server.tokens } = JSON.parse(line))
  for (let i = 0; i < 100; i += 1) {
    try {
      if ((await fetch(`${server.baseUrl}/health`)).ok) return child
    } catch {
      // not listening yet
    }
    await new Promise((r) => setTimeout(r, 100))
  }
  throw new Error('The test server did not start.')
}

async function rest(person, method, path, body) {
  const res = await fetch(`${server.baseUrl}${path}`, {
    method,
    headers: {
      Authorization: `Bearer ${server.tokens[person]}`,
      ...(body === undefined ? {} : { 'Content-Type': 'application/json' }),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  const text = await res.text()
  if (!res.ok) throw new Error(`${method} ${path} -> ${res.status} ${text.slice(0, 160)}`)
  return text ? JSON.parse(text) : null
}

// -- live sessions ---------------------------------------------------------

const sockets = new Map() // person -> live session store

function connect(person, sessionId) {
  const live = createLiveSession({
    sessionId,
    apiBaseUrl: server.baseUrl,
    getToken: async () => server.tokens[person],
  })
  live.start()
  sockets.set(person, live)
  return live
}

function until(live, predicate, label) {
  return new Promise((resolve, reject) => {
    let unsubscribe = () => {}
    const timer = setTimeout(() => {
      unsubscribe()
      reject(new Error(`timed out waiting for ${label}`))
    }, TIMEOUT_MS)
    const check = () => {
      if (!predicate(live.getState())) return
      unsubscribe()
      clearTimeout(timer)
      resolve(live.getState())
    }
    unsubscribe = live.subscribe(check)
    check()
  })
}

const phase = (name) => (state) => livePhase(state) === name

// -- the run ---------------------------------------------------------------

async function setUpClass() {
  await rest('host', 'GET', '/me')
  await rest('host', 'POST', '/e2e/faculty/host')
  const course = await rest('host', 'POST', '/classes', { name: `Load test (${STUDENTS} students)` })
  const base = `/classes/${course.class_id}`

  // Each student signs in for the first time and joins with the class code;
  // the organizer then approves everyone at once.
  await everyone('sign in + join class', students, async (person) => {
    await rest(person, 'GET', '/me')
    await rest(person, 'POST', '/classes/join', { code: course.join_code })
  })
  await rest('host', 'POST', `${base}/join-requests/approve-all`)

  const draft = await rest('host', 'POST', `${base}/quizzes`, {
    title: 'Load test quiz',
    questions: Array.from({ length: QUESTIONS }, (_, i) => ({
      question_text: `Question ${i + 1}?`,
      // Long enough that each question closes because everyone answered.
      time_limit_seconds: Math.max(60, Math.ceil((TIMEOUT_MS * 2) / 1000)),
      choices: ['A', 'B', 'C', 'D'].map((text, c) => ({ choice_text: text, is_correct: c === 0 })),
    })),
  })
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

async function runSession(game) {
  const sid = game.session_id
  const host = connect('host', sid)
  await until(host, phase('lobby'), 'host lobby')

  let playing = await everyone('join session (HTTP)', students, (person) =>
    rest(person, 'POST', '/sessions/join', { join_code: game.join_code }),
  )
  playing = await everyone('connect socket + lobby', playing, (person) =>
    until(connect(person, sid), phase('lobby'), 'lobby'),
  )
  const seen = await until(host, (s) => s.participants.length >= playing.length, 'host sees everyone')
  console.log(`  ${seen.participants.length} students in the lobby`)

  for (let order = 1; order <= QUESTIONS; order += 1) {
    // How long the question takes to reach each student after the host
    // presses "next question". The waits start before the command is sent.
    const isOpen = (s) => s.currentQuestion?.question_order === order
    const opened = performance.now()
    const arrivals = everyoneSince('question reaches student', playing, opened, (person) =>
      until(sockets.get(person), isOpen, `Q${order} open`),
    )
    await host.openNextQuestion()
    playing = await arrivals
    // Everyone answers at once; time until the server accepts each answer.
    playing = await everyone('answer accepted', playing, (person) => {
      const live = sockets.get(person)
      const choices = live.getState().currentQuestion.choices
      return live.submitAnswer(choices[Math.floor(Math.random() * choices.length)].choice_id)
    })
    // The question closes by itself once all have answered. Timed from the
    // moment the last answer was accepted until each student has the results.
    const hasResults = (s) =>
      s.lastQuestion?.question_order === order &&
      s.lastResults?.session_question_id === s.lastQuestion?.session_question_id
    playing = await everyone('results reach student', playing, (person) =>
      until(sockets.get(person), hasResults, `Q${order} results`),
    )
    record('whole question (open → all results)', performance.now() - opened)
    console.log(`  question ${order}/${QUESTIONS} done`)
  }

  const ended = performance.now()
  const finals = everyoneSince('final results reach student', playing, ended, (person) =>
    until(sockets.get(person), (s) => s.final && s.connection === 'ended', 'final'),
  )
  await host.end()
  const final = await until(host, (s) => s.final && s.connection === 'ended', 'host final')
  playing = await finals
  return { final, stillPlaying: playing.length }
}

function report({ final, stillPlaying }, totalMs) {
  const rows = [...timings].map(([step, values]) => {
    const sorted = [...values].sort((a, b) => a - b)
    return {
      step,
      count: sorted.length,
      median: pct(sorted, 50),
      p95: pct(sorted, 95),
      worst: sorted[sorted.length - 1],
      failed: failures.get(step) ?? 0,
    }
  })
  const ms = (v) => (v >= 1000 ? `${(v / 1000).toFixed(2)} s` : `${Math.round(v)} ms`)
  const pad = (s, n) => String(s).padEnd(n)
  const padL = (s, n) => String(s).padStart(n)

  console.log(`\nLive quiz load test: ${STUDENTS} students, ${QUESTIONS} questions\n`)
  console.log(`${pad('Step', 38)}${padL('count', 7)}${padL('median', 10)}${padL('p95', 10)}${padL('worst', 10)}${padL('failed', 8)}`)
  console.log('-'.repeat(83))
  for (const r of rows) {
    console.log(`${pad(r.step, 38)}${padL(r.count, 7)}${padL(ms(r.median), 10)}${padL(ms(r.p95), 10)}${padL(ms(r.worst), 10)}${padL(r.failed, 8)}`)
  }
  const standings = final?.final?.standings?.length ?? 0
  const failed = [...failures.values()].reduce((a, b) => a + b, 0)
  console.log('-'.repeat(83))
  console.log(`Students who finished: ${stillPlaying}/${STUDENTS}   Final leaderboard rows: ${standings}   Total time: ${ms(totalMs)}`)
  for (const [step, message] of firstError) console.log(`  first error in "${step}": ${message}`)
  const passed = failed === 0 && stillPlaying === STUDENTS && standings === STUDENTS
  console.log(passed ? '\nPASS: every student joined, answered every question and got the results.' : '\nFAIL: see the failed column and errors above.')
  return passed
}

const started = performance.now()
let child
let passed = false
try {
  console.log(`Starting the test server and ${STUDENTS} students…`)
  child = await startServer()
  const game = await setUpClass()
  console.log('  class, quiz and session ready')
  const outcome = await runSession(game)
  passed = report(outcome, performance.now() - started)
} catch (error) {
  console.error(`\nThe run stopped: ${error.message}`)
  report({ final: null, stillPlaying: 0 }, performance.now() - started)
} finally {
  for (const live of sockets.values()) live.close()
  child?.kill()
}
process.exit(passed ? 0 : 1)
