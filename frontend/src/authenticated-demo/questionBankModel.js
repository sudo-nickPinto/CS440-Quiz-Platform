export function toEditorQuestion(item) {
  const correct = item.choices.findIndex((choice) => choice.is_correct);
  return {
    id: crypto.randomUUID(),
    text: item.question_text,
    explanation: item.explanation ?? "",
    options: item.choices.map((choice) => choice.choice_text),
    correct,
    // Reused content inherits the destination quiz's current defaults.
    limit: null,
    basePoints: 1000,
  };
}
