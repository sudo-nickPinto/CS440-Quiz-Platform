// Shared plumbing for the e2e tests: starts backend/tests/e2e_server.py (the
// real FastAPI app, with a test key standing in for Auth0), and gives each
// test REST, download and live-socket helpers that act as a named person.
//
// Needs the backend's Python environment. Set BACKEND_PYTHON if it isn't at
// backend/.venv/bin/python. Set E2E_DATABASE_URL to run against a migrated
// MySQL database instead of a throwaway SQLite file (see e2e_server.py).

import { spawn } from 'node:child_process'
import { once } from 'node:events'
import { existsSync } from 'node:fs'
import { createInterface } from 'node:readline'
import { fileURLToPath } from 'node:url'
import { afterAll, beforeAll } from 'vitest'
import { livePhase } from '../src/live/liveReducer.js'
import { createLiveSession } from '../src/live/liveSession.js'

const backendDir = fileURLToPath(new URL('../../backend', import.meta.url))
const python = process.env.BACKEND_PYTHON || `${backendDir}/.venv/bin/python`

export const server = { baseUrl: null, tokens: null }
let child
const liveSessions = []

// Starts the server before the file's tests and stops it (and every socket
// opened through connect()) after them.
export function runE2EServer() {
  beforeAll(async () => {
    if (!existsSync(python)) {
      throw new Error(`No backend Python at ${python}; set BACKEND_PYTHON.`)
    }
    child = spawn(python, ['-m', 'tests.e2e_server'], {
      cwd: backendDir,
      stdio: ['ignore', 'pipe', 'inherit'],
    })
    const [line] = await once(createInterface({ input: child.stdout }), 'line')
    ;({ base_url: server.baseUrl, tokens: server.tokens } = JSON.parse(line))
    for (let i = 0; i < 100; i += 1) {
      try {
        if ((await fetch(`${server.baseUrl}/health`)).ok) return
      } catch {
        // not listening yet
      }
      await new Promise((r) => setTimeout(r, 100))
    }
    throw new Error('e2e server did not start')
  }, 30_000)

  afterAll(() => {
    for (const live of liveSessions) live.close()
    child?.kill()
  })
}

// One HTTP request as `person` (null for no token). Never throws on a status.
export async function call(person, method, path, body) {
  const headers = {}
  if (person) headers.Authorization = `Bearer ${server.tokens[person]}`
  if (body !== undefined) headers['Content-Type'] = 'application/json'
  const res = await fetch(`${server.baseUrl}${path}`, {
    method,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  const bytes = Buffer.from(await res.arrayBuffer())
  const type = res.headers.get('content-type') || ''
  return {
    status: res.status,
    headers: res.headers,
    bytes,
    json: type.includes('application/json') && bytes.length ? JSON.parse(bytes) : null,
  }
}

// The JSON body of a successful request; throws with the error otherwise.
export async function rest(person, method, path, body) {
  const res = await call(person, method, path, body)
  if (res.status >= 400) {
    throw new Error(`${person} ${method} ${path} -> ${res.status} ${res.bytes}`)
  }
  return res.json
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
