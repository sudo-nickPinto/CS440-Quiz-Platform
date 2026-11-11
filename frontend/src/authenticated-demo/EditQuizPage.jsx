import { Link, useParams } from "react-router";
import { classPagePath } from "../classes/classHelpers";

import { useResource } from "./rest";
import { quizToEditor } from "./quizPayload";
import { canEditQuiz, quizEditorKey } from "./quizEditing";
import { QuizEditor } from "./QuizEditor";
import RequestError from "./RequestError";

export default function EditQuizPage() {
  const { quizId } = useParams();

  const validId = /^[1-9]\d*$/.test(quizId ?? "");
  const resource = useResource(
    validId ? `/quizzes/${quizId}` : null,
  );

  if (!validId) {
    return <p role="alert">Invalid quiz ID.</p>;
  }

  if (resource.loading) {
    return <p role="status">Loading quiz for editing…</p>;
  }

  if (resource.error) {
    return (
      <RequestError
        error={resource.error}
        retry={resource.reload}
      />
    );
  }

  const quiz = resource.data;

  if (!quiz) {
    return <p role="alert">The quiz could not be loaded.</p>;
  }

  if (!quiz.can_edit) {
    return (
      <section className="qp-content">
        <h1>Editing unavailable</h1>
        <p>Only the quiz creator or an active collaborator can edit this quiz.</p>
        <Link to={`/app/quizzes/${quiz.quiz_id}`}>
          Back to quiz
        </Link>
      </section>
    );
  }

  if (!canEditQuiz(quiz)) {
    return (
      <section className="qp-content">
        <h1>Editing unavailable</h1>
        <p>Archived quizzes cannot be edited.</p>
        <Link to={classPagePath(quiz.class_id)}>
          Back to class
        </Link>
      </section>
    );
  }

  let initialEditor;

  try {
    initialEditor = quizToEditor(quiz);
  } catch (error) {
    return (
      <section className="qp-content">
        <h1>Editing unavailable</h1>
        <p role="alert">{error.message}</p>
        <Link to={`/app/quizzes/${quiz.quiz_id}`}>
          Back to quiz
        </Link>
      </section>
    );
  }

  return (
    <QuizEditor
      key={quizEditorKey(quiz)}
      initialEditor={initialEditor}
      existingQuiz={quiz}
      onReload={resource.reload}
    />
  );
}
