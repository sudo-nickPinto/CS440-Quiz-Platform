// WebSocket client for one live session (docs/LIVE_PROTOCOL.md).
//
// Handles the parts every screen needs and none should repeat: the auth
// first message (§2), pings every 25 s, matching ack/error replies to the
// command that caused them (§3), and what to do with each close code (§7).
// No React here, so it runs the same in the browser and in Node tests.

export const CloseCode = Object.freeze({
  NORMAL: 1000,
  SERVER_ERROR: 1011,
  MALFORMED: 4400,
  UNAUTHORIZED: 4401,
  FORBIDDEN: 4403,
  NOT_FOUND: 4404,
  REPLACED: 4409,
  SESSION_OVER: 4410,
})

// Connection status values, as reported through onStatus.
//   connecting / open / reconnecting: the socket is (re)starting or usable
//   ended: the session is over (1000 or 4410); show the final screen
//   replaced: this account opened the session in another tab (4409)
//   forbidden / not_found: send the user to the dashboard (4403 / 4404)
//   unauthorized: the token was refused twice; send the user to login
//   failed: a protocol bug (4400); nothing to retry
//   closed: we called close() ourselves
const FINAL_STATUS = {
  [CloseCode.NORMAL]: 'ended',
  [CloseCode.SESSION_OVER]: 'ended',
  [CloseCode.REPLACED]: 'replaced',
  [CloseCode.FORBIDDEN]: 'forbidden',
  [CloseCode.NOT_FOUND]: 'not_found',
  [CloseCode.MALFORMED]: 'failed',
}

export const PING_INTERVAL_MS = 25_000
export const MAX_BACKOFF_MS = 30_000

// 1 s, 2 s, 4 s ... capped at 30 s (§7).
export function backoffDelay(attempt) {
  return Math.min(1000 * 2 ** attempt, MAX_BACKOFF_MS)
}

// http://host:8001 -> ws://host:8001/ws/sessions/12 (https -> wss).
export function liveSocketUrl(apiBaseUrl, sessionId) {
  const base = apiBaseUrl.replace(/\/+$/, '').replace(/^http/, 'ws')
  return `${base}/ws/sessions/${sessionId}`
}

export class LiveCommandError extends Error {
  constructor(code, message) {
    super(message)
    this.name = 'LiveCommandError'
    this.code = code
  }
}

export function createLiveClient({
  url,
  getToken,
  onMessage = () => {},
  onStatus = () => {},
  WebSocketImpl = globalThis.WebSocket,
  timers = globalThis,
  pingIntervalMs = PING_INTERVAL_MS,
}) {
  let socket = null
  let stopped = false
  let attempt = 0
  let retriedAuth = false
  let ready = false
  let pingTimer = null
  let retryTimer = null
  let nextRequestId = 1
  const pending = new Map()

  function setStatus(status, detail) {
    onStatus(status, detail)
  }

  function rejectPending(reason) {
    for (const { reject } of pending.values()) {
      reject(new LiveCommandError('connection_lost', reason))
    }
    pending.clear()
  }

  function stopPing() {
    if (pingTimer !== null) timers.clearInterval(pingTimer)
    pingTimer = null
  }

  async function connect({ freshToken = false } = {}) {
    if (stopped) return
    let token
    try {
      token = await getToken({ freshToken })
    } catch (err) {
      setStatus('unauthorized', err)
      return
    }
    if (stopped) return

    const ws = new WebSocketImpl(url)
    socket = ws
    ready = false

    ws.onopen = () => {
      ws.send(JSON.stringify({ type: 'auth', token }))
    }

    ws.onmessage = (event) => {
      let message
      try {
        message = JSON.parse(event.data)
      } catch {
        return
      }
      if (message.type === 'session_state') {
        // Only a snapshot proves the socket works; reset the retry state here.
        ready = true
        attempt = 0
        retriedAuth = false
        stopPing()
        pingTimer = timers.setInterval(() => {
          if (ready) ws.send(JSON.stringify({ type: 'ping' }))
        }, pingIntervalMs)
        setStatus('open')
      }
      if ((message.type === 'ack' || message.type === 'error') && message.request_id) {
        const waiter = pending.get(message.request_id)
        if (waiter) {
          pending.delete(message.request_id)
          if (message.type === 'ack') waiter.resolve(message)
          else waiter.reject(new LiveCommandError(message.code, message.message))
        }
      }
      if (message.type !== 'pong') onMessage(message)
    }

    ws.onclose = (event) => {
      if (socket !== ws) return // an older socket we already replaced
      socket = null
      ready = false
      stopPing()
      rejectPending(`socket closed (${event.code})`)
      if (stopped) return

      const finalStatus = FINAL_STATUS[event.code]
      if (finalStatus) {
        stopped = true
        if (event.code === CloseCode.MALFORMED) {
          console.error('Live socket closed as malformed (4400):', event.reason)
        }
        setStatus(finalStatus, event)
        return
      }
      if (event.code === CloseCode.UNAUTHORIZED) {
        // Get a fresh token and try once more, then give up (§7).
        if (retriedAuth) {
          stopped = true
          setStatus('unauthorized', event)
          return
        }
        retriedAuth = true
        setStatus('reconnecting', event)
        connect({ freshToken: true })
        return
      }
      // 1011, 1006 (network drop), 1001 (server restart): back off and retry.
      const delay = backoffDelay(attempt)
      attempt += 1
      setStatus('reconnecting', { ...event, delay })
      retryTimer = timers.setTimeout(() => {
        retryTimer = null
        connect()
      }, delay)
    }
  }

  // Sends a command and resolves with its ack, or rejects with a
  // LiveCommandError carrying the server's error code.
  function send(command) {
    if (!socket || !ready) {
      return Promise.reject(
        new LiveCommandError('not_connected', 'Not connected to the live session.'),
      )
    }
    const requestId = `r${nextRequestId++}`
    const reply = new Promise((resolve, reject) => {
      pending.set(requestId, { resolve, reject })
    })
    socket.send(JSON.stringify({ ...command, request_id: requestId }))
    return reply
  }

  function close() {
    stopped = true
    stopPing()
    if (retryTimer !== null) timers.clearTimeout(retryTimer)
    retryTimer = null
    rejectPending('client closed')
    if (socket) {
      const ws = socket
      socket = null
      ws.close(CloseCode.NORMAL)
    }
    setStatus('closed')
  }

  setStatus('connecting')
  connect()
  return { send, close }
}
