// Pure state for one live session screen, built from server messages.
//
// session_state replaces everything (clients render from the snapshot alone,
// §5); each later event patches it. Events may repeat what a fresh snapshot
// already shows (§2), so every case is safe to apply twice.

export const initialLiveState = {
  connection: 'connecting', // see liveClient.js for the values
  role: null, // 'host' | 'participant'
  session: null, // { session_id, status, current_question_order, total_questions, join_code? }
  participantCount: 0,
  participants: [], // host only: [{ session_participant_id, display_name }]
  hostConnected: true,
  currentQuestion: null, // question_opened payload while a question is OPEN
  myAnswer: null, // participant: { choice_id, submitted_at } for the open question
  answerProgress: null, // host: { answered_count, eligible_count }
  lastQuestion: null, // question_opened payload of the latest CLOSED question
  lastClosed: null, // its question_closed event (reason, counts)
  lastResults: null, // its question_results view
  final: null, // session_ended payload, or GET /sessions/{id}/results
  lastError: null, // latest { code, message } from a refused command
}

const ENDED = ['COMPLETED', 'CANCELLED']

function withStatus(state, patch) {
  return state.session ? { ...state.session, ...patch } : state.session
}

function upsertParticipant(list, { session_participant_id, display_name }) {
  if (list.some((p) => p.session_participant_id === session_participant_id)) return list
  return [...list, { session_participant_id, display_name }]
}

function onServerMessage(state, message) {
  switch (message.type) {
    case 'session_state': {
      const closedQuestion = message.last_question
      return {
        ...initialLiveState,
        connection: state.connection,
        participants: state.participants,
        final: state.final,
        role: message.role,
        session: message.session,
        participantCount: message.participant_count,
        hostConnected: message.host_connected,
        currentQuestion: message.current_question,
        myAnswer: message.my_answer,
        lastQuestion: closedQuestion,
        lastResults: message.last_results,
      }
    }

    case 'participant_joined':
      return {
        ...state,
        participantCount: message.participant_count,
        participants: upsertParticipant(state.participants, message),
      }

    case 'participant_left':
      return {
        ...state,
        participantCount: message.participant_count,
        participants: state.participants.filter(
          (p) => p.session_participant_id !== message.session_participant_id,
        ),
      }

    case 'host_status':
      return { ...state, hostConnected: message.connected }

    case 'question_opened': {
      if (state.currentQuestion?.session_question_id === message.session_question_id) {
        return state // already shown by the snapshot
      }
      const question = { ...message }
      delete question.type
      return {
        ...state,
        session: withStatus(state, {
          status: 'ACTIVE',
          current_question_order: message.question_order,
        }),
        currentQuestion: question,
        myAnswer: null,
        answerProgress: null,
        lastQuestion: null,
        lastClosed: null,
        lastResults: null,
        lastError: null,
      }
    }

    case 'answer_progress':
      if (state.currentQuestion?.session_question_id !== message.session_question_id) {
        return state
      }
      return {
        ...state,
        answerProgress: {
          answered_count: message.answered_count,
          eligible_count: message.eligible_count,
        },
      }

    case 'question_closed': {
      const id = message.session_question_id
      if (state.currentQuestion?.session_question_id === id) {
        return {
          ...state,
          currentQuestion: null,
          lastQuestion: state.currentQuestion,
          lastClosed: message,
          lastResults: null,
          answerProgress: {
            answered_count: message.answered_count,
            eligible_count: message.eligible_count,
          },
        }
      }
      if (state.lastQuestion?.session_question_id === id) {
        return { ...state, lastClosed: message }
      }
      return state
    }

    case 'question_results':
      if (
        state.lastQuestion &&
        state.lastQuestion.session_question_id !== message.session_question_id
      ) {
        return state
      }
      return { ...state, lastResults: message }

    case 'session_ended':
      return {
        ...state,
        session: withStatus(state, { status: message.reason }),
        currentQuestion: null,
        final: message,
      }

    case 'ack':
      // A submit_answer ack carries the receipt; remember the choice so a
      // participant sees "answer submitted" straight away.
      if (
        message.receipt &&
        state.currentQuestion?.session_question_id === message.receipt.session_question_id
      ) {
        return {
          ...state,
          myAnswer: {
            choice_id: message.receipt.choice_id,
            submitted_at: message.receipt.submitted_at,
          },
        }
      }
      return state

    case 'error':
      return { ...state, lastError: { code: message.code, message: message.message } }

    default:
      return state
  }
}

export function liveReducer(state, action) {
  switch (action.type) {
    case 'server':
      return onServerMessage(state, action.message)
    case 'connection':
      return { ...state, connection: action.status }
    case 'participants':
      return { ...state, participants: action.participants }
    case 'final_results':
      return {
        ...state,
        session: withStatus(state, { status: action.results.status }),
        currentQuestion: null,
        final: action.results,
      }
    case 'command_failed':
      return { ...state, lastError: { code: action.code, message: action.message } }
    default:
      return state
  }
}

// One word for which screen to draw.
export function livePhase(state) {
  if (state.connection === 'left') return 'left'
  if (state.final || ENDED.includes(state.session?.status) || state.connection === 'ended') {
    return 'ended'
  }
  if (!state.session) return 'connecting'
  if (state.currentQuestion) return 'question'
  if (state.lastQuestion) return 'results'
  if (state.session.status === 'LOBBY') return 'lobby'
  return 'waiting'
}

// Order of the question the host should open next, or null after the last.
export function nextQuestionOrder(state) {
  if (!state.session) return null
  const next = (state.session.current_question_order ?? 0) + 1
  return next <= state.session.total_questions ? next : null
}
