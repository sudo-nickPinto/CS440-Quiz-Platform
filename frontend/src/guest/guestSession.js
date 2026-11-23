// Guest players for the capstone live demo (temporary, demo branch only).
//
// A guest joins with a game code and a nickname instead of an account. The
// backend answers with its own token, kept for this browser tab only, which
// the app then sends wherever it would send an Auth0 access token.

import { createContext, useContext } from 'react'

const KEY = 'quizburg-guest-token'
const SESSION_KEY = 'quizburg-guest-session'

// In guest mode, the path of the guest's own game (/app/play/<id>), which is
// the only place their buttons lead; null for signed-in users.
export const GuestQuizContext = createContext(null)

export function useGuestQuizPath() {
  return useContext(GuestQuizContext)
}

export function getGuestToken() {
  try {
    return sessionStorage.getItem(KEY) || ''
  } catch {
    return ''
  }
}

export function setGuestToken(token, sessionId) {
  try {
    sessionStorage.setItem(KEY, token)
    sessionStorage.setItem(SESSION_KEY, String(sessionId))
  } catch {
    // Without storage the guest can't stay signed in; join reports it.
  }
}

// The one game this guest joined, as /app/play/<id>, or '' if unknown.
export function getGuestQuizPath() {
  try {
    const id = sessionStorage.getItem(SESSION_KEY) || ''
    return /^[1-9][0-9]*$/.test(id) ? `/app/play/${id}` : ''
  } catch {
    return ''
  }
}

export function clearGuestToken() {
  try {
    sessionStorage.removeItem(KEY)
    sessionStorage.removeItem(SESSION_KEY)
  } catch {
    // Nothing to clear without storage.
  }
}

// The token source for apiFetch and the live socket: the guest token while
// nobody is signed in with Auth0, otherwise Auth0's own getter.
export function pickTokenGetter(isAuthenticated, getAccessTokenSilently) {
  const guestToken = isAuthenticated ? '' : getGuestToken()
  return guestToken ? async () => guestToken : getAccessTokenSilently
}

// The two guest endpoints need no sign-in.
export async function guestPost(path, payload) {
  const base = import.meta.env.VITE_API_BASE_URL.replace(/\/+$/, '')
  const response = await fetch(`${base}/guest${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  const body = await response.json().catch(() => null)

  if (!response.ok) {
    const error = new Error(
      body?.error?.message || `${response.status} ${response.statusText}`,
    )
    error.code = body?.error?.code
    error.status = response.status
    throw error
  }

  return body
}
