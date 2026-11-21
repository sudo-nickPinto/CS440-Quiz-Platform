import { spawn } from 'node:child_process'
import { once } from 'node:events'
import { existsSync } from 'node:fs'
import { createInterface } from 'node:readline'
import { fileURLToPath } from 'node:url'

const backendDir = fileURLToPath(new URL('../../backend', import.meta.url))
const python = process.env.BACKEND_PYTHON || `${backendDir}/.venv/bin/python`

// The FastAPI test server issues synthetic tokens and serves the real routes.
export async function startE2EServer() {
  if (!existsSync(python)) {
    throw new Error(`No backend Python at ${python}; set BACKEND_PYTHON.`)
  }
  const child = spawn(python, ['-m', 'tests.e2e_server'], {
    cwd: backendDir,
    stdio: ['ignore', 'pipe', 'inherit'],
  })
  const lines = createInterface({ input: child.stdout })
  async function stop() {
    if (child.exitCode !== null || child.signalCode !== null || !child.pid) return
    const exited = once(child, 'exit')
    child.kill()
    await exited
  }

  try {
    const [line] = await Promise.race([
      once(lines, 'line', { signal: AbortSignal.timeout(15_000) }),
      once(child, 'exit').then(([code]) => {
        throw new Error(`FastAPI test server exited before starting (${code}).`)
      }),
    ])
    const { base_url: baseUrl, tokens } = JSON.parse(line)
    for (let attempt = 0; attempt < 100; attempt += 1) {
      try {
        if ((await fetch(`${baseUrl}/health`)).ok) return { baseUrl, tokens, stop }
      } catch {
        // The server has printed its address but may not be listening yet.
      }
      await new Promise((resolve) => setTimeout(resolve, 100))
    }
    throw new Error('FastAPI test server did not become healthy.')
  } catch (error) {
    await stop()
    throw error
  } finally {
    lines.close()
  }
}

// One HTTP request as `person` (null for no token). Never throws on a status.
export async function callApi(server, person, method, path, body) {
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
export async function restApi(server, person, method, path, body) {
  const res = await callApi(server, person, method, path, body)
  if (res.status >= 400) {
    throw new Error(`${person} ${method} ${path} -> ${res.status} ${res.bytes}`)
  }
  return res.json
}
