export function toQuizCreate(editor) {
  const title = editor.title.trim();

  if (!title || title.length > 200) {
    throw new Error("Enter a title of 1–200 characters.");
  }

  if (!editor.questions.length) {
    throw new Error("Add at least one question.");
  }

  return {
    title,
    questions: editor.questions.map((question, index) => {
      const label = `Question ${index + 1}`;
      const text = question.text.trim();
      const explanation = (question.explanation ?? "").trim();

      if (explanation.length > 5000) {
        throw new Error(
          `${label}: explanation must be 5,000 characters or fewer.`,
        );
      }
      const seconds = Number(question.limit ?? editor.defaultTime);

      if (!text) {
        throw new Error(`${label}: enter the question text.`);
      }

      if (!Number.isInteger(seconds) || seconds < 5 || seconds > 300) {
        throw new Error(`${label}: use a whole number from 5 to 300 seconds.`);
      }

      if (question.options.length < 2 || question.options.length > 4) {
        throw new Error(`${label}: provide two to four choices.`);
      }

      if (
        !Number.isInteger(question.correct) ||
        question.correct < 0 ||
        question.correct >= question.options.length
      ) {
        throw new Error(`${label}: select the correct answer.`);
      }

      return {
        question_text: text,
        explanation: explanation || null,
        time_limit_seconds: seconds,
        base_points: 1000,
        choices: question.options.map((option, choiceIndex) => {
          const choice = option.trim();

          if (!choice || choice.length > 500) {
            throw new Error(`${label}: choices must have 1–500 characters.`);
          }

          return {
            choice_text: choice,
            is_correct: choiceIndex === question.correct,
          };
        }),
      };
    }),
  };
}
