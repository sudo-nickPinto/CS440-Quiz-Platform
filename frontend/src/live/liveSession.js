// A small store for one live session: the socket client, the reducer, and
// the REST calls the socket doesn't cover. useLiveSession() is a thin React
// wrapper around this, and the tests drive it directly.

import { LiveCommandError, createLiveClient, liveSocketUrl } from './liveClient.js'
import { initialLiveState, liveReducer, nextQuestionOrder } from './liveReducer.js'

export function createLiveSession({
  sessionId,
  apiBaseUrl,
  getToken, // ({ freshToken }) => Promise<string>
  WebSocketImpl,
  fetchImpl = (...args) => globalThis.fetch(...args),
  timers,
}) {
  let state = initialLiveState
  const listeners = new Set()
  let leaving = false
  let fetchingFinal = false

  function dispatch(action) {
    state = liveReducer(state, action)
    for (const listener of listeners) listener()
  }

  async function getJson(path) {
    const token = await getToken({ freshToken: false })
    const res = await fetchImpl(`${apiBaseUrl.replace(/\/+$/, '')}${path}`, {
      headers: { Authorization: `Bearer ${token}` },
    })
    if (!res.ok) throw new Error(`${res.status} ${path}`)
    return res.json()
  }

  // The session_ended event is lost if we were offline when it went out, and
  // a reconnect then closes with 4410; the stored results fill the gap.
  async function loadFinalResults() {
    if (state.final || fetchingFinal) return
    fetchingFinal = true
    try {
      dispatch({ type: 'final_results', results: await getJson(`/sessions/${sessionId}/results`) })
    } catch (err) {
      dispatch({ type: 'command_failed', code: 'results_unavailable', message: err.message })
    } finally {
      fetchingFinal = false
    }
  }

  // Joins and leaves that arrive while a roster fetch is in flight. The
  // fetched rows may predate them, so they're replayed on top (null when no
  // fetch is running).
  let rosterEvents = null
  let rosterFetch = 0

  // The snapshot has only a count; the host's lobby wants the names too.
  async function loadRoster() {
    const fetchId = ++rosterFetch
    rosterEvents = []
    try {
      const rows = await getJson(`/sessions/${sessionId}/participants`)
      if (fetchId !== rosterFetch) return // a newer snapshot started another
      let participants = rows.map(({ session_participant_id, display_name }) => ({
        session_participant_id,
        display_name,
      }))
      for (const event of rosterEvents) {
        participants = participants.filter(
          (p) => p.session_participant_id !== event.session_participant_id,
        )
        if (event.type === 'participant_joined') {
          participants.push({
            session_participant_id: event.session_participant_id,
            display_name: event.display_name,
          })
        }
      }
      dispatch({ type: 'participants', participants })
    } catch {
      // Non-fatal: participant_joined events still fill the list in.
    } finally {
      if (fetchId === rosterFetch) rosterEvents = null
    }
  }

  let client = null

  // Opens the socket. Safe to call again after close(), which React's
  // StrictMode does by mounting effects twice.
  function start() {
    if (client) return
    client = createLiveClient({
      url: liveSocketUrl(apiBaseUrl, sessionId),
      getToken,
      WebSocketImpl,
      timers,
      onMessage(message) {
        if (
          rosterEvents &&
          (message.type === 'participant_joined' || message.type === 'participant_left')
        ) {
          rosterEvents.push(message)
        }
        dispatch({ type: 'server', message })
        if (message.type === 'session_state' && message.role === 'host') loadRoster()
      },
      onStatus(status) {
        // A participant who leaves is closed with 1000 too; that isn't the end.
        const shown = status === 'ended' && leaving ? 'left' : status
        dispatch({ type: 'connection', status: shown })
        if (shown === 'ended') loadFinalResults()
      },
    })
  }

  function close() {
    const current = client
    client = null
    current?.close()
  }

  async function command(message) {
    try {
      if (!client) {
        throw new LiveCommandError('not_connected', 'Not connected to the live session.')
      }
      return await client.send(message)
    } catch (err) {
      dispatch({ type: 'command_failed', code: err.code, message: err.message })
      throw err
    }
  }

  return {
    getState: () => state,
    subscribe(listener) {
      listeners.add(listener)
      return () => listeners.delete(listener)
    },
    start,
    close,

    // Host controls
    openQuestion: (questionOrder) =>
      command({ type: 'open_question', question_order: questionOrder }),
    openNextQuestion() {
      const order = nextQuestionOrder(state)
      if (order === null) {
        return Promise.reject(new Error('There are no more questions.'))
      }
      return command({ type: 'open_question', question_order: order })
    },
    skip() {
      const question = state.currentQuestion
      if (!question) return Promise.reject(new Error('No question is open.'))
      return command({
        type: 'close_question',
        session_question_id: question.session_question_id,
      })
    },
    end: () => command({ type: 'end_session' }),
    cancel: () => command({ type: 'cancel_session' }),

    // Participant actions
    submitAnswer(choiceId) {
      const question = state.currentQuestion
      if (!question) return Promise.reject(new Error('No question is open.'))
      return command({
        type: 'submit_answer',
        session_question_id: question.session_question_id,
        choice_id: choiceId,
      })
    },
    leave() {
      leaving = true
      return command({ type: 'leave' }).catch((err) => {
        leaving = false
        throw err
      })
    },
  }
}
