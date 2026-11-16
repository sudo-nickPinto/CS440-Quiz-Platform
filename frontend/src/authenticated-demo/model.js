// Empty-quiz shapes for the quiz editor.
export const LETTERS = "ABCDEF";

// Question and answer text stay short enough to read on the live screen.
// The hard limits are the longest text that still fits a 1280x720 host
// screen at its smallest font (a 200-character question with four
// 120-character answers, measured with the "Fit Test" quizzes). Past the
// soft limits the host screen starts using smaller text, so the editor
// says so.
export const QUESTION_LIMIT = 200;
export const ANSWER_LIMIT = 120;
export const QUESTION_SOFT_LIMIT = 120;
export const ANSWER_SOFT_LIMIT = 60;

// The counter next to a question or answer appears past the soft limit
// ("long": it will show smaller) and turns red over the hard limit, which
// only older quizzes can be.
export function charCount(length, limit, soft) {
  return {
    visible: length > soft,
    long: length > soft && length <= limit,
    over: length > limit,
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
