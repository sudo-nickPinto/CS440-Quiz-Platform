import { answerSuit } from "../live/questionDisplay";

// White card-suit shape for an answer position. Inline SVG (not ♠♥♦♣ text)
// so no platform swaps in a coloured emoji.
const SHAPES = {
  spade: (
    <path d="M12 2C9.2 5.8 3.5 8.8 3.5 13.4 3.5 16.2 5.6 18 8 18c1.4 0 2.6-.6 3.3-1.6L10 22h4l-1.3-5.6c.7 1 1.9 1.6 3.3 1.6 2.4 0 4.5-1.8 4.5-4.6C20.5 8.8 14.8 5.8 12 2Z" />
  ),
  heart: (
    <path d="M12 21.5S2.5 15.6 2.5 9.2C2.5 6 4.9 3.5 7.9 3.5c1.8 0 3.2.9 4.1 2.3.9-1.4 2.3-2.3 4.1-2.3 3 0 5.4 2.5 5.4 5.7 0 6.4-9.5 12.3-9.5 12.3Z" />
  ),
  diamond: <path d="M12 1.5 20.5 12 12 22.5 3.5 12Z" />,
  club: (
    <>
      <circle cx="12" cy="7" r="4.4" />
      <circle cx="6.7" cy="13.6" r="4.4" />
      <circle cx="17.3" cy="13.6" r="4.4" />
      {/* Fills the gap where the three leaves meet. */}
      <circle cx="12" cy="12.2" r="3.2" />
      <path d="M10.7 12h2.6l1.4 10H9.3Z" />
    </>
  ),
};

export default function AnswerSuit({ index }) {
  const suit = answerSuit(index);

  return (
    <svg
      className={`lv-suit lv-suit-${suit}`}
      viewBox="0 0 24 24"
      fill="currentColor"
      aria-hidden="true"
      focusable="false"
    >
      {SHAPES[suit]}
    </svg>
  );
}
