import { useRef, useState } from "react";

import { WHEEL_SPACING, wheelPosition, wheelTarget } from "./wheelMath";
import "./question-wheel.css";

const RESULT = {
  correct: "✓ Correct",
  wrong: "✗ Wrong",
  missed: "— No answer",
  not_played: "· Not played",
};

// Phones only (see question-wheel.css): a dark bar pinned to the bottom of
// the report card. The question numbers slide under a fixed orange lens;
// drag the strip or tap a number to switch questions without scrolling
// back up. While dragging, the page dims and a card shows the question
// you would land on.
export default function QuestionWheel({ questions, answers, selected, onSelect }) {
  const [drag, setDrag] = useState(null);
  const dragged = useRef(false);
  const count = questions.length;

  if (count < 2) return null;

  const position = drag?.moved ? drag.position : selected;
  const landing = wheelTarget(position, count);

  function onPointerDown(event) {
    dragged.current = false;
    setDrag({ id: event.pointerId, startX: event.clientX, position: selected, moved: false });
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
    }
    setDrag({ ...drag, moved: true, position: wheelPosition(selected, dx, count) });
  }

  function onPointerEnd() {
    if (!drag) return;
    if (drag.moved) onSelect(wheelTarget(drag.position, count));
    setDrag(null);
  }

  const peek = questions[landing];

  return (
    <div className="qw" data-dragging={drag?.moved ? "true" : undefined}>
      {drag?.moved && (
        <>
          <div className="qw-shade" aria-hidden="true" />
          <div className="qw-peek" aria-hidden="true">
            <b data-state={answers[landing].state}>
              Q{peek.order} · {RESULT[answers[landing].state]}
            </b>
            <span>{peek.text}</span>
          </div>
        </>
      )}

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
                aria-label={`Question ${question.order}: ${RESULT[state].slice(2)}`}
                style={{
                  transform: `translateX(${offset * WHEEL_SPACING}px) scale(${
                    Math.abs(offset) < 0.5 ? 1.18 - Math.abs(offset) * 0.36 : 1
                  })`,
                  opacity: Math.max(0.25, 1 - Math.abs(offset) * 0.14),
                }}
                onClick={() => {
                  if (!dragged.current) onSelect(index);
                }}
              >
                {question.order}
              </button>
            );
          })}
          <span className="qw-lens" aria-hidden="true" />
        </div>
        <span className="qw-count" aria-hidden="true">
          {landing + 1}/{count}
        </span>
      </nav>
    </div>
  );
}
