export function quizToEditor(quiz) {
  const version = quiz.version;

  return {
    title: version.title,
    description: version.description ?? "",
    defaultTime: 20,
    questions: [...version.questions]
      .sort((a, b) => a.question_order - b.question_order)
      .map((question, index) => {
        const choices = [...question.choices].sort(
          (a, b) => a.choice_order - b.choice_order,
        );

        const correctChoices = choices.filter(
          (choice) => choice.is_correct,
        );

        // Preserve the current editor's supported question format.
        // Refuse unsupported questions instead of silently changing them.
        if (
          question.question_type !== "MULTIPLE_CHOICE" ||
          choices.length < 2 ||
          choices.length > 4 ||
          correctChoices.length !== 1
        ) {
          throw new Error(
            `Question ${index + 1} cannot be edited here. ` +
              "This editor supports two to four choices with one correct answer.",
          );
        }

        return {
          id: `saved-${question.question_id}`,
          text: question.question_text,
          explanation: question.explanation ?? "",
          options: choices.map((choice) => choice.choice_text),
          correct: choices.findIndex((choice) => choice.is_correct),
          limit: question.time_limit_seconds,
          basePoints: question.base_points,
        };
      }),
  };
}

export function toQuizCreate(editor) {
  const title = editor.title.trim();

  if (!title || title.length > 200) {
    throw new Error("Enter a title of 1–200 characters.");
  }

  if (
    editor.questions.length < 1 ||
    editor.questions.length > 65_535
  ) {
    throw new Error("Provide between 1 and 65,535 questions.");
  }

  return {
    title,
    description: (editor.description ?? "").trim() || null,

    questions: editor.questions.map((question, index) => {
      const label = `Question ${index + 1}`;
      const text = question.text.trim();
      const explanation = (question.explanation ?? "").trim();
      const seconds = Number(question.limit ?? editor.defaultTime);
      const points = Number(question.basePoints ?? 1000);

      if (!text) {
        throw new Error(`${label}: enter the question text.`);
      }

      if (explanation.length > 5000) {
        throw new Error(
          `${label}: explanation must be 5,000 characters or fewer.`,
        );
      }

      // Match the existing backend limits so loading and saving
      // a valid stored quiz does not discard its timing.
      if (
        !Number.isInteger(seconds) ||
        seconds < 1 ||
        seconds > 65_535
      ) {
        throw new Error(
          `${label}: use a whole number from 1 to 65,535 seconds.`,
        );
      }

      if (
        !Number.isInteger(points) ||
        points < 1 ||
        points > 4_294_967_295
      ) {
        throw new Error(
          `${label}: use a whole number from 1 to 4,294,967,295 base points.`,
        );
      }

      if (
        question.options.length < 2 ||
        question.options.length > 4
      ) {
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
        base_points: points,

        choices: question.options.map((option, choiceIndex) => {
          const choice = option.trim();

          if (!choice || choice.length > 500) {
            throw new Error(
              `${label}: choices must have 1–500 characters.`,
            );
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
