import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { CloseCode } from './liveClient.js'
import { livePhase } from './liveReducer.js'
import { createLiveSession } from './liveSession.js'

class FakeSocket {
  static all = []

  constructor(url) {
    this.url = url
    this.sent = []
    FakeSocket.all.push(this)
  }

  send(text) {
    this.sent.push(JSON.parse(text))
  }

  close() {}

  serve(message) {
    this.onmessage?.({ data: JSON.stringify(message) })
  }

  drop(code) {
    this.onclose?.({ code, reason: '' })
  }
}

const snapshot = (role, extra = {}) => ({
  type: 'session_state',
  role,
  session: { session_id: 9, status: 'ACTIVE', current_question_order: 1, total_questions: 3 },
  participant_count: 1,
  host_connected: true,
  current_question: null,
  my_answer: null,
  last_question: null,
  last_results: null,
  ...extra,
})

function jsonResponse(body) {
  return Promise.resolve({ ok: true, json: () => Promise.resolve(body) })
}

async function startSession(role, extra) {
  const fetchImpl = vi.fn((url) =>
    url.endsWith('/participants')
      ? jsonResponse([{ session_participant_id: 4, account_id: 2, display_name: 'Ann', joined_at: 't' }])
      : jsonResponse({ session_id: 9, status: 'COMPLETED', ended_at: 't', me: null, leaderboard: [] }),
  )
  const live = createLiveSession({
    sessionId: 9,
    apiBaseUrl: 'http://api/',
    getToken: async () => 'tok',
    WebSocketImpl: FakeSocket,
    fetchImpl,
  })
  live.start()
  await vi.advanceTimersByTimeAsync(0)
  const ws = FakeSocket.all.at(-1)
  ws.onopen()
  ws.serve(snapshot(role, extra))
  await vi.advanceTimersByTimeAsync(0)
  return { live, ws, fetchImpl }
}

beforeEach(() => {
  vi.useFakeTimers()
  FakeSocket.all = []
})

afterEach(() => {
  vi.useRealTimers()
})

describe('createLiveSession', () => {
  it('does nothing until started', () => {
    createLiveSession({ sessionId: 9, apiBaseUrl: 'http://api', getToken: async () => 't', WebSocketImpl: FakeSocket })
    expect(FakeSocket.all).toHaveLength(0)
  })

  it('loads the roster for a host with a bearer token', async () => {
    const { live, fetchImpl, ws } = await startSession('host')
    expect(ws.url).toBe('ws://api/ws/sessions/9')
    expect(fetchImpl).toHaveBeenCalledWith('http://api/sessions/9/participants', {
      headers: { Authorization: 'Bearer tok' },
    })
    expect(live.getState().participants).toEqual([{ session_participant_id: 4, display_name: 'Ann' }])
  })

  it('opens the next question and skips the current one by id', async () => {
    const { live, ws } = await startSession('host', {
      current_question: { session_question_id: 31, question_order: 1, choices: [] },
    })
    live.skip()
    live.openNextQuestion()
    expect(ws.sent.slice(1)).toEqual([
      { type: 'close_question', session_question_id: 31, request_id: 'r1' },
      { type: 'open_question', question_order: 2, request_id: 'r2' },
    ])
  })

  it('submits the chosen answer for the open question', async () => {
    const { live, ws } = await startSession('participant', {
      current_question: { session_question_id: 31, question_order: 1, choices: [] },
    })
    const reply = live.submitAnswer(77)
    expect(ws.sent.at(-1)).toEqual({ type: 'submit_answer', session_question_id: 31, choice_id: 77, request_id: 'r1' })
    ws.serve({ type: 'ack', request_id: 'r1', receipt: { session_question_id: 31, choice_id: 77, submitted_at: 't' } })
    await expect(reply).resolves.toMatchObject({ type: 'ack' })
    expect(live.getState().myAnswer.choice_id).toBe(77)
  })

  it('records a refused command as lastError', async () => {
    const { live, ws } = await startSession('participant')
    const reply = live.end()
    ws.serve({ type: 'error', request_id: 'r1', code: 'session_host_denied', message: 'Only the host.' })
    await expect(reply).rejects.toMatchObject({ code: 'session_host_denied' })
    expect(live.getState().lastError.code).toBe('session_host_denied')
  })

  it('fetches the stored results when told the session is over (4410)', async () => {
    const { live, ws, fetchImpl } = await startSession('participant')
    ws.drop(CloseCode.SESSION_OVER)
    await vi.advanceTimersByTimeAsync(0)
    expect(fetchImpl).toHaveBeenCalledWith('http://api/sessions/9/results', expect.anything())
    expect(live.getState().final.status).toBe('COMPLETED')
    expect(livePhase(live.getState())).toBe('ended')
  })

  it('does not refetch results that session_ended already delivered', async () => {
    const { live, ws, fetchImpl } = await startSession('participant')
    ws.serve({ type: 'session_ended', reason: 'COMPLETED', leaderboard: [], me: null })
    ws.drop(CloseCode.NORMAL)
    await vi.advanceTimersByTimeAsync(0)
    expect(fetchImpl).not.toHaveBeenCalled()
    expect(live.getState().final.reason).toBe('COMPLETED')
  })

  it('shows "left", not "ended", after leaving', async () => {
    const { live, ws, fetchImpl } = await startSession('participant')
    const reply = live.leave()
    ws.serve({ type: 'ack', request_id: 'r1' })
    ws.drop(CloseCode.NORMAL)
    await reply
    await vi.advanceTimersByTimeAsync(0)
    expect(livePhase(live.getState())).toBe('left')
    expect(fetchImpl).not.toHaveBeenCalled()
  })

  it('can be restarted after close, as StrictMode does', async () => {
    const { live } = await startSession('participant')
    live.close()
    await expect(live.end()).rejects.toMatchObject({ code: 'not_connected' })
    live.start()
    await vi.advanceTimersByTimeAsync(0)
    expect(FakeSocket.all).toHaveLength(2)
  })
})
