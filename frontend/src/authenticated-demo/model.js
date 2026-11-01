// Empty-quiz shapes for the quiz editor.
export const LETTERS = "ABCDEF";

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
