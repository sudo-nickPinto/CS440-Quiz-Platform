// Shared plumbing for the e2e tests: starts backend/tests/e2e_server.py (the
// real FastAPI app, with a test key standing in for Auth0), and gives each
// test REST, download and live-socket helpers that act as a named person.
//
// Needs the backend's Python environment. Set BACKEND_PYTHON if it isn't at
// backend/.venv/bin/python. Set E2E_DATABASE_URL to run against a migrated
// MySQL database instead of a throwaway SQLite file (see e2e_server.py).

import { afterAll, beforeAll } from 'vitest'
import { livePhase } from '../src/live/liveReducer.js'
import { createLiveSession } from '../src/live/liveSession.js'

import { callApi, restApi, startE2EServer } from './server.js'

export const server = { baseUrl: null, tokens: null }
const liveSessions = []

// Starts the server before the file's tests and stops it (and every socket
// opened through connect()) after them.
export function runE2EServer() {
  beforeAll(async () => {
    Object.assign(server, await startE2EServer())
  }, 30_000)

  afterAll(async () => {
    for (const live of liveSessions) live.close()
    await server.stop?.()
  })
}

export async function call(person, method, path, body) {
  return callApi(server, person, method, path, body)
}

export async function rest(person, method, path, body) {
  return restApi(server, person, method, path, body)
}

// { status, code, details } of a request that must fail.
export async function refused(person, method, path, body) {
  const res = await call(person, method, path, body)
  if (res.status < 400) {
    throw new Error(`${person} ${method} ${path} should have failed: ${res.status} ${res.bytes}`)
  }
  return { status: res.status, code: res.json?.error?.code, details: res.json?.error?.details }
}

// The live-session store the React hook uses, connected as `person`.
export function connect(person, sessionId) {
  const live = createLiveSession({
    sessionId,
    apiBaseUrl: server.baseUrl,
    getToken: async () => server.tokens[person],
  })
  live.start()
  liveSessions.push(live)
  return live
}

// Resolves once predicate(state) holds; fails with the last state otherwise.
export function until(live, predicate, label, timeoutMs = 5000) {
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

export const phase = (name) => (state) => livePhase(state) === name
