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

export function validateQuiz(quiz) {
  const errors = [];

  if (!quiz.title.trim()) errors.push("Give the quiz a title.");
  if (!quiz.questions.length) errors.push("Add at least one question.");

  quiz.questions.forEach((q, i) => {
    const prefix = `Question ${i + 1}:`;

    if (!q.text.trim()) errors.push(`${prefix} enter the question.`);

    if (
      q.options.length < 2 ||
      q.options.length > 6 ||
      q.options.some((text) => !text.trim())
    ) {
      errors.push(`${prefix} enter between two and six complete choices.`);
    }

    if (
      !Number.isInteger(q.correct) ||
      q.correct < 0 ||
      q.correct >= q.options.length
    ) {
      errors.push(`${prefix} mark the correct answer.`);
    }

    const seconds = Number(q.limit ?? quiz.defaultTime);

    if (!Number.isInteger(seconds) || seconds < 5 || seconds > 300) {
      errors.push(`${prefix} use a time between 5 and 300 seconds.`);
    }
  });

  return errors;
}

export function answerFor(q, pick, seconds) {
  const correct = pick === q.correct;

  return {
    pick,
    seconds: pick === null ? null : seconds,
    correct,
    // Preview formula only. Real scoring must come from the backend.
    points: correct
      ? Math.round(1000 * (1 - Math.min(seconds / q.limit, 1) / 2))
      : 0,
  };
}

export function standings(session) {
  const rows = session.players.map((player) => {
    const answers = session.history.map((round) => round[player.id]);

    return {
      ...player,
      answers,
      points: answers.reduce((sum, answer) => sum + answer.points, 0),
      correct: answers.filter((answer) => answer.correct).length,
    };
  });

  return rows
    .map((row) => ({
      ...row,
      rank: 1 + rows.filter((other) => other.points > row.points).length,
    }))
    .sort((a, b) => b.points - a.points || a.name.localeCompare(b.name));
}

export function makeSession(id, quiz, mode, now) {
  const names = ["Maya Patel", "Jordan Lee", "Sofia Ramirez", "Ethan Brooks"];

  return {
    id,
    quiz: structuredClone(quiz),
    mode,
    code: mode === "participant" ? "482913" : "739201",
    createdAt: new Date(now).toISOString(),
    phase: "lobby",
    index: 0,
    history: [],
    pick: null,
    deadline: null,
    players: [
      ...names.map((name, i) => ({ id: `bot-${i}`, name })),
      ...(mode === "participant" ? [{ id: "me", name: "You" }] : []),
    ],
  };
}

function closeQuestion(session, now) {
  if (session.phase !== "question") return session;

  const q = session.quiz.questions[session.index];
  const elapsed = Math.min(
    q.limit,
    Math.max(0, (now - session.startedAt) / 1000),
  );

  const answers = Object.fromEntries(
    session.players.map((player, i) => {
      if (player.id === "me") {
        return [player.id, session.pick || answerFor(q, null, null)];
      }

      const seconds = q.limit * (0.2 + i * 0.13);
      const missed = (i + session.index) % 7 === 6 || seconds > elapsed;

      const pick = missed
        ? null
        : (i + session.index) % 4 === 0
          ? (q.correct + 1) % q.options.length
          : q.correct;

      return [player.id, answerFor(q, pick, seconds)];
    }),
  );

  return {
    ...session,
    phase: "feedback",
    deadline: null,
    history: [...session.history, answers],
  };
}

export function createInitialState() {
  const quiz = {
    id: "data-structures",
    title: "Data Structures",
    owner: "you",
    status: "published",
    questions: [
      [
        "Which data structure follows LIFO?",
        ["Stack", "Queue", "Linked List", "Heap"],
        0,
      ],
      [
        "Worst-case search in a balanced BST?",
        ["O(1)", "O(log n)", "O(n)", "O(n log n)"],
        1,
      ],
      [
        "Which data structure follows FIFO?",
        ["Stack", "Queue", "Binary Tree", "Hash Table"],
        1,
      ],
      [
        "Which structure gives average O(1) lookup by key?",
        ["Array", "Linked List", "Hash Table", "Binary Heap"],
        2,
      ],
      [
        "Which traversal visits BST keys in sorted order?",
        ["Pre-order", "In-order", "Post-order", "Level-order"],
        1,
      ],
    ].map(([text, options, correct], i) => ({
      id: `sample-q${i}`,
      text,
      options,
      correct,
      limit: 20,
    })),
  };

  const sessions = ["host", "participant"].map((mode) => {
    let s = makeSession(`sample-${mode}`, quiz, mode, 1791453600000);

    quiz.questions.forEach((q, index) => {
      s = closeQuestion(
        {
          ...s,
          index,
          phase: "question",
          startedAt: 0,
          pick:
            mode === "participant"
              ? answerFor(q, index === 2 ? null : q.correct, 6)
              : null,
        },
        q.limit * 1000,
      );
    });

    return { ...s, phase: "ended" };
  });

  return {
    version: 1,
    quizzes: [quiz],
    sessions,
    editor: blankEditor(),
  };
}

export function reducer(state, action) {
  if (action.type === "RESET") return action.state;

  if (action.type === "EDITOR") {
    return { ...state, editor: action.editor };
  }

  if (action.type === "SAVE") {
    if (validateQuiz(state.editor).length) return state;

    const quiz = {
      ...structuredClone(state.editor),
      id: action.id,
      title: state.editor.title.trim(),
      owner: "you",
      status: "published",
      questions: state.editor.questions.map((q) => ({
        ...q,
        text: q.text.trim(),
        options: q.options.map((text) => text.trim()),
        limit: Number(q.limit ?? state.editor.defaultTime),
      })),
    };

    return {
      ...state,
      quizzes: [quiz, ...state.quizzes],
      editor: action.nextEditor,
    };
  }

  if (action.type === "ARCHIVE") {
    return {
      ...state,
      quizzes: state.quizzes.map((q) =>
        q.id === action.id ? { ...q, status: "archived" } : q,
      ),
    };
  }

  if (action.type === "CREATE_SESSION") {
    return {
      ...state,
      sessions: [action.session, ...state.sessions],
    };
  }

  return {
    ...state,
    sessions: state.sessions.map((s) => {
      if (s.id !== action.id) return s;

      const q = s.quiz.questions[s.index];

      switch (action.type) {
        case "START":
          return s.phase === "lobby"
            ? {
                ...s,
                phase: "countdown",
                deadline: action.now + 3000,
              }
            : s;

        case "TICK":
          if (s.phase === "countdown" && action.now >= s.deadline) {
            return {
              ...s,
              phase: "question",
              startedAt: action.now,
              deadline: action.now + q.limit * 1000,
              pick: null,
            };
          }

          return s.phase === "question" && action.now >= s.deadline
            ? closeQuestion(s, action.now)
            : s;

        case "PICK":
          if (
            s.mode !== "participant" ||
            s.phase !== "question" ||
            s.pick ||
            action.now >= s.deadline ||
            !Number.isInteger(action.pick) ||
            action.pick < 0 ||
            action.pick >= q.options.length
          ) {
            return s;
          }

          return {
            ...s,
            pick: answerFor(
              q,
              action.pick,
              Math.max(0, (action.now - s.startedAt) / 1000),
            ),
          };

        case "CLOSE":
          return closeQuestion(s, action.now);

        case "BOARD":
          return s.phase === "feedback" ? { ...s, phase: "board" } : s;

        case "NEXT":
          if (!["feedback", "board"].includes(s.phase)) return s;

          return s.index + 1 === s.quiz.questions.length
            ? { ...s, phase: "ended" }
            : {
                ...s,
                index: s.index + 1,
                phase: "countdown",
                pick: null,
                deadline: action.now + 3000,
              };

        case "END": {
          if (s.phase === "ended") return s;
          const closed = closeQuestion(s, action.now);
          return { ...closed, phase: "ended", deadline: null };
        }

        default:
          return s;
      }
    }),
  };
}
