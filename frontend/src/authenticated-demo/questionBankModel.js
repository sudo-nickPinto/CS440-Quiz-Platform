export function toEditorQuestion(item) {
  const correctChoices = item.choices
    .map((choice, index) => choice.is_correct ? index : -1)
    .filter((index) => index !== -1);
  if (correctChoices.length !== 1) {
    throw new Error("This quiz editor supports exactly one correct answer per question.");
  }

  return {
    id: crypto.randomUUID(),
    text: item.question_text,
    explanation: item.explanation ?? "",
    options: item.choices.map((choice) => choice.choice_text),
    correct: correctChoices[0],
    // Reused content inherits the destination quiz's current defaults.
    limit: null,
    basePoints: 1000,
  };
}
