import {
  questionPayloadChanged,
  quizQuestionToEditor,
  toQuestionCreate,
  toQuizCreate,
} from "./quizPayload";

export function remoteStructureDecision({
  editor,
  baselineEditor,
  currentRevision,
  incomingRevision,
}) {
  const reload = JSON.stringify(editor) === JSON.stringify(baselineEditor);
  return {
    reload,
    revision: reload ? incomingRevision : currentRevision,
  };
}

export function canApplyRemoteQuestion(localQuestion, baselineQuestion) {
  return Boolean(
    localQuestion &&
      baselineQuestion &&
      JSON.stringify(localQuestion) === JSON.stringify(baselineQuestion),
  );
}

export function nextAggregateRevision(
  currentRevision,
  incomingRevision,
  aggregateStale,
) {
  return aggregateStale ? currentRevision : incomingRevision;
}

export function canSaveDraftIndependently(editor, baselineEditor) {
  const appendOnlyStructure =
    editor.questions.length >= baselineEditor.questions.length &&
    baselineEditor.questions.every(
      (question, index) =>
        question.questionId === editor.questions[index]?.questionId,
    ) &&
    editor.questions
      .slice(baselineEditor.questions.length)
      .every((question) => !question.questionId);
  const sameMetadata =
    editor.title === baselineEditor.title &&
    editor.description === baselineEditor.description;

  return appendOnlyStructure && sameMetadata;
}

export function aggregateQuizUpdatePayload(editor, revision) {
  return {
    ...toQuizCreate(editor),
    expected_revision: revision,
  };
}

export function saveAggregateQuiz({ editor, revision, existingQuiz, api }) {
  return api(
    `/classes/${existingQuiz.class_id}/quizzes/${existingQuiz.quiz_id}`,
    {
      method: "PUT",
      body: JSON.stringify(aggregateQuizUpdatePayload(editor, revision)),
    },
  );
}

export async function saveDraftQuestions({
  editor,
  baselineEditor,
  existingQuiz,
  api,
  onProgress = () => {},
}) {
  let currentEditor = editor;
  let currentBaseline = baselineEditor;
  let lastResult = null;

  function reconcile(result, submittedQuestion, index, appended) {
    const saved = quizQuestionToEditor(
      result.question,
      index,
      currentEditor.defaultTime,
    );
    currentEditor = {
      ...currentEditor,
      questions: currentEditor.questions.map((question, questionIndex) =>
        questionIndex === index && question.id === submittedQuestion.id
          ? saved
          : question,
      ),
    };
    currentBaseline = {
      ...currentBaseline,
      questions: appended
        ? [...currentBaseline.questions, saved]
        : currentBaseline.questions.map((question) =>
            question.questionId === saved.questionId ? saved : question,
          ),
    };
    lastResult = result;
    onProgress({
      editor: currentEditor,
      baselineEditor: currentBaseline,
      quizRevision: result.quiz_revision,
    });
  }

  const savedQuestionCount = currentBaseline.questions.length;
  for (let index = 0; index < savedQuestionCount; index += 1) {
    const question = currentEditor.questions[index];
    const savedQuestion = currentBaseline.questions[index];
    if (
      !questionPayloadChanged(
        question,
        savedQuestion,
        index,
        currentEditor.defaultTime,
        currentBaseline.defaultTime,
      )
    ) {
      continue;
    }

    const payload = toQuestionCreate(
      question,
      index,
      currentEditor.defaultTime,
    );
    payload.expected_revision = question.revision;
    const result = await api(
      `/classes/${existingQuiz.class_id}/quizzes/${existingQuiz.quiz_id}` +
        `/questions/${question.questionId}`,
      { method: "PATCH", body: JSON.stringify(payload) },
    );
    reconcile(result, question, index, false);
  }

  while (currentBaseline.questions.length < currentEditor.questions.length) {
    const index = currentBaseline.questions.length;
    const question = currentEditor.questions[index];
    const payload = toQuestionCreate(
      question,
      index,
      currentEditor.defaultTime,
    );
    const result = await api(
      `/classes/${existingQuiz.class_id}/quizzes/${existingQuiz.quiz_id}` +
        "/questions",
      { method: "POST", body: JSON.stringify(payload) },
    );
    reconcile(result, question, index, true);
  }

  return {
    lastResult,
    editor: currentEditor,
    baselineEditor: currentBaseline,
  };
}
