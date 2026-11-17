import { useRef, useState } from "react";

import { WHEEL_SPACING, wheelPosition, wheelTarget } from "./wheelMath";
import "./question-wheel.css";

const RESULT = {
  correct: "Correct",
  wrong: "Wrong",
  missed: "No answer",
  not_played: "Not played",
};

// Phones only (see question-wheel.css): a dark bar pinned to the bottom of
// the report card. The question numbers slide under a fixed orange lens;
// drag the strip or tap a number to switch questions without scrolling
// back up. The page's own question card follows the lens live while
// dragging (onSelect), and onEngage brings that card fully into view as
// soon as a drag starts.
export default function QuestionWheel({ questions, answers, selected, onSelect, onEngage }) {
  const [drag, setDrag] = useState(null);
  const dragged = useRef(false);
  const count = questions.length;

  if (count < 2) return null;

  const position = drag?.moved ? drag.position : selected;

  function onPointerDown(event) {
    dragged.current = false;
    setDrag({
      id: event.pointerId,
      startX: event.clientX,
      startIndex: selected,
      position: selected,
      moved: false,
    });
  }

  function onPointerMove(event) {
    if (!drag || event.pointerId !== drag.id) return;
    const dx = event.clientX - drag.startX;
    if (!drag.moved && Math.abs(dx) < 6) return;
    if (!drag.moved) {
      // From here on the strip owns the pointer, so lifting the finger
      // over a number doesn't also tap it.
      event.currentTarget.setPointerCapture?.(event.pointerId);
      dragged.current = true;
      onEngage?.({ smooth: true });
    }
    const next = wheelPosition(drag.startIndex, dx, count);
    const landing = wheelTarget(next, count);
    if (landing !== selected) onSelect(landing, { live: true });
    setDrag({ ...drag, moved: true, position: next });
  }

  function onPointerEnd() {
    if (!drag) return;
    if (drag.moved) onSelect(wheelTarget(drag.position, count), { live: true });
    setDrag(null);
  }

  return (
    <div className="qw" data-dragging={drag?.moved ? "true" : undefined}>
      <nav className="qw-bar" aria-label="Switch question">
        <div
          className="qw-track"
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={onPointerEnd}
          onPointerCancel={onPointerEnd}
        >
          {questions.map((question, index) => {
            const offset = index - position;
            if (Math.abs(offset) > 6) return null;
            const state = answers[index].state;
            return (
              <button
                type="button"
                key={question.question_id}
                className="qw-num"
                data-state={state}
                aria-current={index === selected ? "true" : undefined}
                aria-label={`Question ${question.order}: ${RESULT[state]}`}
                style={{
                  transform: `translateX(${offset * WHEEL_SPACING}px) scale(${
                    Math.abs(offset) < 0.5 ? 1.18 - Math.abs(offset) * 0.36 : 1
                  })`,
                  opacity: Math.max(0.25, 1 - Math.abs(offset) * 0.14),
                }}
                onClick={() => {
                  if (!dragged.current) onSelect(index, { live: false });
                }}
              >
                {question.order}
              </button>
            );
          })}
          <span className="qw-lens" aria-hidden="true" />
        </div>
        <span className="qw-count" aria-hidden="true">
          {selected + 1}/{count}
        </span>
      </nav>
    </div>
  );
}
