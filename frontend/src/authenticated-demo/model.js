// Empty-quiz shapes for the quiz editor.
export const LETTERS = "ABCDEF";

// Question and answer text stay short enough to read on the live screen.
export const TEXT_LIMIT = 120;

// The counter under a question or answer appears once the text gets close
// to the limit. Older quizzes can still hold longer text, so "over" shows
// that too.
export function charCount(length, limit = TEXT_LIMIT) {
  const left = limit - length;
  return {
    visible: left <= 20,
    over: left < 0,
    label: `${length}/${limit}`,
  };
}

export function newQuestion() {
  return {
    id: crypto.randomUUID(),
    text: "",
    explanation: "",
    options: ["", "", "", ""],
    correct: null,
    limit: null,
  };
}

export function blankEditor() {
  return {
    title: "",
    defaultTime: 20,
    questions: [newQuestion()],
  };
}
