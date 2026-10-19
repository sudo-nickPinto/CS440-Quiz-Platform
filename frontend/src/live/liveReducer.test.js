import { describe, expect, it } from 'vitest'
import { initialLiveState, livePhase, liveReducer, nextQuestionOrder } from './liveReducer.js'

const server = (message) => ({ type: 'server', message })

function apply(...messages) {
  return messages.reduce((state, message) => liveReducer(state, server(message)), initialLiveState)
}

const snapshot = (overrides = {}) => ({
  type: 'session_state',
  role: 'participant',
  session: { session_id: 1, status: 'LOBBY', current_question_order: null, total_questions: 2 },
  participant_count: 2,
  host_connected: true,
  current_question: null,
  my_answer: null,
  last_question: null,
  last_results: null,
  ...overrides,
})

const opened = (order, id = order * 10) => ({
  type: 'question_opened',
  session_id: 1,
  session_question_id: id,
  question_order: order,
  total_questions: 2,
  question_text: `Q${order}?`,
  choices: [{ choice_id: 5, choice_order: 1, choice_text: 'A' }],
  opened_at: '2026-10-14T12:00:00.000Z',
  closes_at: '2026-10-14T12:00:30.000Z',
})

const closed = (id, reason = 'HOST') => ({
  type: 'question_closed',
  session_question_id: id,
  reason,
  answered_count: 1,
  eligible_count: 2,
})

describe('liveReducer', () => {
  it('starts in the lobby from a snapshot', () => {
    const state = apply(snapshot())
    expect(state.role).toBe('participant')
    expect(state.participantCount).toBe(2)
    expect(livePhase(state)).toBe('lobby')
  })

  it('walks a question from open to results', () => {
    let state = apply(snapshot(), opened(1))
    expect(livePhase(state)).toBe('question')
    expect(state.session).toMatchObject({ status: 'ACTIVE', current_question_order: 1 })
    expect(state.currentQuestion).not.toHaveProperty('type')

    state = liveReducer(
      state,
      server({ type: 'ack', request_id: 'r1', receipt: { session_question_id: 10, choice_id: 5, submitted_at: 't' } }),
    )
    expect(state.myAnswer).toEqual({ choice_id: 5, submitted_at: 't' })

    state = liveReducer(state, server(closed(10)))
    expect(state.currentQuestion).toBeNull()
    expect(state.lastQuestion.question_text).toBe('Q1?')
    expect(state.lastClosed.reason).toBe('HOST')
    expect(livePhase(state)).toBe('results')

    const results = { type: 'question_results', session_question_id: 10, me: { rank: 1 } }
    state = liveReducer(state, server(results))
    expect(state.lastResults).toBe(results)

    state = liveReducer(state, server(opened(2)))
    expect(state.lastResults).toBeNull()
    expect(state.myAnswer).toBeNull()
    expect(nextQuestionOrder(state)).toBeNull()
  })

  it('ignores events a fresh snapshot already showed', () => {
    const state = apply(
      snapshot({ current_question: { ...opened(1), type: undefined }, my_answer: { choice_id: 5 } }),
    )
    const again = liveReducer(state, server(opened(1)))
    expect(again).toBe(state)
    expect(again.myAnswer).toEqual({ choice_id: 5 })

    const afterClose = liveReducer(again, server(closed(10)))
    expect(liveReducer(afterClose, server(closed(10)))).toEqual(afterClose)
  })

  it('drops results and progress for a question that is not current', () => {
    const state = apply(snapshot(), opened(2, 20))
    expect(liveReducer(state, server({ type: 'answer_progress', session_question_id: 99, answered_count: 1, eligible_count: 1 }))).toBe(state)
    const afterClose = liveReducer(state, server(closed(20)))
    expect(liveReducer(afterClose, server({ type: 'question_results', session_question_id: 10 }))).toBe(afterClose)
  })

  it('keeps the host roster in step with joins and leaves', () => {
    const joined = (id, name, count) => ({
      type: 'participant_joined',
      session_participant_id: id,
      display_name: name,
      participant_count: count,
    })
    let state = apply(snapshot({ role: 'host', participant_count: 0 }), joined(1, 'Ann', 1), joined(2, 'Bo', 2), joined(2, 'Bo', 2))
    expect(state.participants.map((p) => p.display_name)).toEqual(['Ann', 'Bo'])
    state = liveReducer(state, server({ type: 'participant_left', session_participant_id: 1, display_name: 'Ann', participant_count: 1 }))
    expect(state.participants.map((p) => p.display_name)).toEqual(['Bo'])
    expect(state.participantCount).toBe(1)
  })

  it('tracks the host connection for participants', () => {
    const state = apply(snapshot(), { type: 'host_status', connected: false })
    expect(state.hostConnected).toBe(false)
  })

  it('ends from session_ended or from REST results', () => {
    const ended = apply(snapshot(), opened(1), { type: 'session_ended', reason: 'COMPLETED', leaderboard: [] })
    expect(livePhase(ended)).toBe('ended')
    expect(ended.session.status).toBe('COMPLETED')
    expect(ended.currentQuestion).toBeNull()

    const restored = liveReducer(initialLiveState, {
      type: 'final_results',
      results: { status: 'CANCELLED', standings: [] },
    })
    expect(livePhase(restored)).toBe('ended')
    expect(restored.final.status).toBe('CANCELLED')
  })

  it('keeps the final results across a late snapshot', () => {
    let state = apply(snapshot(), { type: 'session_ended', reason: 'COMPLETED', leaderboard: [] })
    state = liveReducer(state, server(snapshot()))
    expect(state.final).not.toBeNull()
  })

  it('records refused commands and connection changes', () => {
    let state = apply(snapshot(), { type: 'error', request_id: 'r1', code: 'session_host_denied', message: 'no' })
    expect(state.lastError.code).toBe('session_host_denied')
    state = liveReducer(state, { type: 'connection', status: 'left' })
    expect(livePhase(state)).toBe('left')
  })
})
