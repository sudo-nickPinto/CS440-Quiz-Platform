import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  CloseCode,
  LiveCommandError,
  backoffDelay,
  createLiveClient,
  liveSocketUrl,
} from './liveClient.js'

// Records what the client sends; tests play the server by calling serve().
class FakeSocket {
  static all = []

  constructor(url) {
    this.url = url
    this.sent = []
    this.closedWith = null
    FakeSocket.all.push(this)
  }

  send(text) {
    this.sent.push(JSON.parse(text))
  }

  close(code) {
    this.closedWith = code
  }

  open() {
    this.onopen?.()
  }

  serve(message) {
    this.onmessage?.({ data: JSON.stringify(message) })
  }

  drop(code, reason = '') {
    this.onclose?.({ code, reason })
  }

  static latest() {
    return FakeSocket.all.at(-1)
  }
}

const SNAPSHOT = { type: 'session_state', role: 'host', session: { session_id: 7 } }

function start(overrides = {}) {
  const statuses = []
  const messages = []
  const getToken = vi.fn(async ({ freshToken }) => (freshToken ? 'fresh' : 'cached'))
  const client = createLiveClient({
    url: 'ws://api/ws/sessions/7',
    getToken,
    WebSocketImpl: FakeSocket,
    onStatus: (status) => statuses.push(status),
    onMessage: (message) => messages.push(message),
    ...overrides,
  })
  return { client, statuses, messages, getToken }
}

// Lets the awaited getToken() inside connect() settle.
const flush = () => vi.advanceTimersByTimeAsync(0)

async function connected(overrides) {
  const ctx = start(overrides)
  await flush()
  const ws = FakeSocket.latest()
  ws.open()
  ws.serve(SNAPSHOT)
  return { ...ctx, ws }
}

beforeEach(() => {
  vi.useFakeTimers()
  FakeSocket.all = []
})

afterEach(() => {
  vi.useRealTimers()
})

describe('liveSocketUrl', () => {
  it('turns the API base into a ws(s) URL', () => {
    expect(liveSocketUrl('http://127.0.0.1:8001', 4)).toBe('ws://127.0.0.1:8001/ws/sessions/4')
    expect(liveSocketUrl('https://quiz.example/', 4)).toBe('wss://quiz.example/ws/sessions/4')
  })
})

describe('backoffDelay', () => {
  it('doubles from 1 s and caps at 30 s', () => {
    expect([0, 1, 2, 3, 4, 5, 6].map(backoffDelay)).toEqual([
      1000, 2000, 4000, 8000, 16000, 30000, 30000,
    ])
  })
})

describe('createLiveClient', () => {
  it('sends auth first, then reports open on the snapshot', async () => {
    const { ws, statuses, messages } = await connected()
    expect(ws.url).toBe('ws://api/ws/sessions/7')
    expect(ws.sent).toEqual([{ type: 'auth', token: 'cached' }])
    expect(statuses).toEqual(['connecting', 'open'])
    expect(messages).toEqual([SNAPSHOT])
  })

  it('pings every 25 s and hides pongs', async () => {
    const { ws, messages } = await connected()
    await vi.advanceTimersByTimeAsync(25_000)
    expect(ws.sent.at(-1)).toEqual({ type: 'ping' })
    ws.serve({ type: 'pong' })
    expect(messages.map((m) => m.type)).toEqual(['session_state'])
  })

  it('matches acks and errors to the command that caused them', async () => {
    const { client, ws } = await connected()
    const opened = client.send({ type: 'open_question', question_order: 1 })
    const refused = client.send({ type: 'end_session' })
    const [first, second] = ws.sent.slice(1)
    expect(first).toEqual({ type: 'open_question', question_order: 1, request_id: 'r1' })

    ws.serve({ type: 'error', request_id: second.request_id, code: 'session_not_started', message: 'no' })
    ws.serve({ type: 'ack', request_id: first.request_id, session_question_id: 3 })

    await expect(opened).resolves.toMatchObject({ session_question_id: 3 })
    await expect(refused).rejects.toMatchObject({ name: 'LiveCommandError', code: 'session_not_started' })
  })

  it('refuses commands before the snapshot arrives', async () => {
    const { client } = start()
    await expect(client.send({ type: 'end_session' })).rejects.toBeInstanceOf(LiveCommandError)
  })

  it('rejects in-flight commands when the socket drops', async () => {
    const { client, ws } = await connected()
    const reply = client.send({ type: 'end_session' })
    ws.drop(1006)
    await expect(reply).rejects.toMatchObject({ code: 'connection_lost' })
  })

  it.each([
    [CloseCode.NORMAL, 'ended'],
    [CloseCode.SESSION_OVER, 'ended'],
    [CloseCode.REPLACED, 'replaced'],
    [CloseCode.FORBIDDEN, 'forbidden'],
    [CloseCode.NOT_FOUND, 'not_found'],
    [CloseCode.MALFORMED, 'failed'],
  ])('close %i is final: status %s and no reconnect', async (code, status) => {
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {})
    const { ws, statuses } = await connected()
    ws.drop(code)
    await vi.advanceTimersByTimeAsync(60_000)
    expect(statuses.at(-1)).toBe(status)
    expect(FakeSocket.all).toHaveLength(1)
    spy.mockRestore()
  })

  it.each([
    [CloseCode.GOING_AWAY, 'idle_timeout'],
    [CloseCode.NORMAL, 'idle_timeout'], // older servers idled out with 1000
  ])('close %i %s is an idle drop: reconnect, not ended', async (code, reason) => {
    const { statuses } = await connected()
    FakeSocket.latest().drop(code, reason)
    expect(statuses.at(-1)).toBe('reconnecting')
    expect(statuses).not.toContain('ended')

    await vi.advanceTimersByTimeAsync(1000)
    expect(FakeSocket.all).toHaveLength(2)
    const ws = FakeSocket.latest()
    ws.open()
    ws.serve(SNAPSHOT)
    expect(statuses.at(-1)).toBe('open')
  })

  it('reconnects with backoff after a drop and resets after a snapshot', async () => {
    const { statuses } = await connected()
    FakeSocket.latest().drop(1006)
    expect(statuses.at(-1)).toBe('reconnecting')

    await vi.advanceTimersByTimeAsync(999)
    expect(FakeSocket.all).toHaveLength(1)
    await vi.advanceTimersByTimeAsync(1)
    expect(FakeSocket.all).toHaveLength(2)

    FakeSocket.latest().drop(CloseCode.SERVER_ERROR) // failed again: wait 2 s
    await vi.advanceTimersByTimeAsync(1999)
    expect(FakeSocket.all).toHaveLength(2)
    await vi.advanceTimersByTimeAsync(1)
    expect(FakeSocket.all).toHaveLength(3)

    const ws = FakeSocket.latest()
    ws.open()
    ws.serve(SNAPSHOT)
    expect(statuses.at(-1)).toBe('open')
    ws.drop(1006) // back to 1 s after a good connection
    await vi.advanceTimersByTimeAsync(1000)
    expect(FakeSocket.all).toHaveLength(4)
  })

  it('retries a refused token once with a fresh one, then gives up', async () => {
    const { statuses, getToken } = await connected()
    FakeSocket.latest().drop(CloseCode.UNAUTHORIZED)
    await flush()
    expect(getToken).toHaveBeenLastCalledWith({ freshToken: true })
    const retry = FakeSocket.latest()
    retry.open()
    expect(retry.sent[0]).toEqual({ type: 'auth', token: 'fresh' })

    retry.drop(CloseCode.UNAUTHORIZED)
    await vi.advanceTimersByTimeAsync(60_000)
    expect(statuses.at(-1)).toBe('unauthorized')
    expect(FakeSocket.all).toHaveLength(2)
  })

  it('reports unauthorized when no token can be had', async () => {
    const { statuses } = start({ getToken: async () => Promise.reject(new Error('login_required')) })
    await flush()
    expect(statuses).toEqual(['connecting', 'unauthorized'])
    expect(FakeSocket.all).toHaveLength(0)
  })

  it('close() stops pings and reconnects', async () => {
    const { client, ws, statuses } = await connected()
    client.close()
    expect(ws.closedWith).toBe(CloseCode.NORMAL)
    ws.drop(CloseCode.NORMAL)
    await vi.advanceTimersByTimeAsync(60_000)
    expect(ws.sent.filter((m) => m.type === 'ping')).toHaveLength(0)
    expect(statuses.at(-1)).toBe('closed')
    expect(FakeSocket.all).toHaveLength(1)
  })
})
