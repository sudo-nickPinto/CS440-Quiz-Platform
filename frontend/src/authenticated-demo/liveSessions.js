// Pages of a running game (hosting or playing). The header hides its exits
// there, and the "a quiz is live" popup stays away, so nobody leaves a game
// by accident.
export const LIVE_GAME_PATH = /^\/app\/(host|play)\//;

export function isLiveGamePath(pathname) {
  return LIVE_GAME_PATH.test(pathname);
}

// Joins a live session as a player without the six-digit code, as the class
// page's Live button and the live-quiz popup do. Resolves truthy once the
// account is in the session (then open /app/play/{sessionId}); throws the API
// error otherwise.
export async function joinSession(api, sessionId) {
  try {
    return await api(`/sessions/${sessionId}/join`, { method: "POST" });
  } catch (error) {
    // Already joined (another tab, or an earlier click): go straight in.
    if (error.code === "session_already_joined") return true;
    throw error;
  }
}
