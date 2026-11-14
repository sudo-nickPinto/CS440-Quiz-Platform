// Display helpers for an open question: the suit shape on each answer box,
// and the short question-only preview before the answers appear.

// One suit per answer position, repeating after four like the answer colours
// (ui-tone-0..3), so A is always the navy spade, B the orange heart, and so on.
export const ANSWER_SUITS = ['spade', 'heart', 'diamond', 'club']

export function answerSuit(index) {
  const position = Number.isInteger(index) && index >= 0 ? index : 0
  return ANSWER_SUITS[position % ANSWER_SUITS.length]
}

// The server opens a question and starts its timer in one step, so the
// preview is drawn by the client only: for the first few seconds the host
// shows the question alone (no timer or answers) and players can't answer yet.
// It takes at most a quarter of the time limit, so short questions keep most
// of their answering time.
export const PREVIEW_MS = 3000
const PREVIEW_SHARE = 0.25

// When the preview ends, in local milliseconds, or null when the question has
// no usable timing. `seenAt` is when this screen first showed the question; it
// caps the preview when the local clock runs behind the server's, and a
// question opened long ago (a reconnect) gets no preview at all.
export function previewEndsAt(question, seenAt) {
  const opened = Date.parse(question?.opened_at)
  const closes = Date.parse(question?.closes_at)
  if (!Number.isFinite(opened) || !Number.isFinite(closes) || closes <= opened) {
    return null
  }
  const length = Math.min(PREVIEW_MS, (closes - opened) * PREVIEW_SHARE)
  return Math.min(opened + length, seenAt + length)
}

export function inPreview(question, seenAt, now) {
  const end = previewEndsAt(question, seenAt)
  return end !== null && now < end
}
