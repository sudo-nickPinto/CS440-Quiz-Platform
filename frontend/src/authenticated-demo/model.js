// Empty-quiz shapes for the quiz editor.
export const LETTERS = "ABCDEF";

// Question and answer text stay short enough to read on the live screen.
// The limits are the longest text that still fits a 1280x720 host screen
// at its smallest font (a 200-character question with four 120-character
// answers, measured with the "Fit Test" quizzes). Explanations only show
// in the results review, so they get more room.
export const QUESTION_LIMIT = 200;
export const ANSWER_LIMIT = 120;
export const EXPLANATION_LIMIT = 1000;

// The counter shows up this many characters before a limit.
export const COUNT_WARN = 20;

// The gray "185/200" counter next to a field.
export function charCount(length, limit) {
  return {
    visible: length >= limit - COUNT_WARN,
    label: `${length.toLocaleString()}/${limit.toLocaleString()}`,
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
