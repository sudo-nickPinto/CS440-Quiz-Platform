import { useAuth0 } from '@auth0/auth0-react'
import { useEffect, useMemo, useSyncExternalStore } from 'react'
import { createLiveSession } from './liveSession.js'
import { livePhase, nextQuestionOrder } from './liveReducer.js'

// Live state and controls for one session page.
//
//   const live = useLiveSession(sessionId)
//   live.phase          'connecting' | 'lobby' | 'question' | 'results'
//                       | 'waiting' | 'ended' | 'left'
//   live.state          see initialLiveState in liveReducer.js
//   live.openNextQuestion(), live.skip(), live.end(), live.cancel()   (host)
//   live.submitAnswer(choiceId), live.leave()                         (participant)
//
// Each action returns a promise that resolves on the server's ack and
// rejects with a LiveCommandError ({ code, message }) on an error reply.
export function useLiveSession(sessionId) {
  const { getAccessTokenSilently } = useAuth0()

  // Building the store has no side effects; the socket opens in the effect.
  const store = useMemo(
    () =>
      createLiveSession({
        sessionId,
        apiBaseUrl: import.meta.env.VITE_API_BASE_URL,
        getToken: ({ freshToken }) =>
          getAccessTokenSilently(freshToken ? { cacheMode: 'off' } : undefined),
      }),
    [sessionId, getAccessTokenSilently],
  )

  useEffect(() => {
    store.start()
    return () => store.close()
  }, [store])

  const state = useSyncExternalStore(store.subscribe, store.getState)

  return useMemo(
    () => ({
      state,
      phase: livePhase(state),
      nextQuestionOrder: nextQuestionOrder(state),
      openQuestion: store.openQuestion,
      openNextQuestion: store.openNextQuestion,
      skip: store.skip,
      end: store.end,
      cancel: store.cancel,
      submitAnswer: store.submitAnswer,
      leave: store.leave,
    }),
    [state, store],
  )
}
