import { useEffect } from 'react'
import { useNavigate } from 'react-router'

import { useAction, useApi, useResource } from './rest'
import RequestError from './RequestError'

const POLL_MS = 5000

// The class page's Live button (task 6). Shows one button per lobby or running
// session in the class; members join without typing the six-digit code.
// Renders nothing while there is no live session or the class is not visible
// to the caller (the endpoint answers 404 for nonmembers).
export default function ClassLiveButton({ classId }) {
  const sessions = useResource(
    classId ? `/classes/${classId}/active-sessions` : null,
    POLL_MS,
  )
  const api = useApi()
  const action = useAction()
  const navigate = useNavigate()
  const { reload } = sessions

  // Check again as soon as the tab comes back, instead of waiting for a poll.
  useEffect(() => {
    window.addEventListener('focus', reload)
    return () => window.removeEventListener('focus', reload)
  }, [reload])

  async function open(session) {
    if (session.is_host) {
      navigate(`/app/host/${session.session_id}`)
      return
    }
    if (!session.joined) {
      const joined = await action.run(async () => {
        try {
          return await api(`/sessions/${session.session_id}/join`, {
            method: 'POST',
          })
        } catch (error) {
          // Joined in another tab since the last poll: go straight in.
          if (error.code === 'session_already_joined') return true
          throw error
        }
      })
      if (!joined) return
    }
    navigate(`/app/play/${session.session_id}`)
  }

  if (!sessions.data?.length) return null

  return (
    <div className="qp-actions">
      {sessions.data.map((session) => (
        <button
          key={session.session_id}
          className="qp-primary"
          type="button"
          disabled={action.busy}
          onClick={() => open(session)}
        >
          {session.is_host ? 'Host' : 'Live'}: {session.quiz_title}
          {session.status === 'ACTIVE' && session.current_question_order
            ? ` (question ${session.current_question_order} of ${session.question_count})`
            : ' (lobby)'}
        </button>
      ))}

      <RequestError error={action.error} />
    </div>
  )
}
