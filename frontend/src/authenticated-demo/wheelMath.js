// Math for the report card's question wheel (QuestionWheel.jsx): a strip of
// question numbers dragged sideways under a fixed lens.

// Pixels between two numbers on the strip.
export const WHEEL_SPACING = 66;

// Where the strip sits while dragging: the index under the lens, as a
// fraction. Dragging left moves to later questions. It can overshoot each
// end a little, so the ends feel springy.
export function wheelPosition(startIndex, dx, count, spacing = WHEEL_SPACING) {
  const position = startIndex - dx / spacing;
  return Math.min(count - 0.6, Math.max(-0.4, position));
}

// The question the strip settles on when let go.
export function wheelTarget(position, count) {
  return Math.min(count - 1, Math.max(0, Math.round(position)));
}
