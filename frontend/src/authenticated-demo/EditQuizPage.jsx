import { Link, useParams } from "react-router";

import { useAccount } from "./account";
import { useResource } from "./rest";
import { quizToEditor } from "./quizPayload";
import { QuizEditor } from "./QuizEditor";
import RequestError from "./RequestError";

export default function EditQuizPage() {
  const { quizId } = useParams();
  const account = useAccount();

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

  if (quiz.author_id !== account.account_id) {
    return (
      <section className="qp-content">
        <h1>Editing unavailable</h1>
        <p>Only the quiz creator can edit this quiz.</p>
        <Link to={`/app/quizzes/${quiz.quiz_id}`}>
          Back to quiz
        </Link>
      </section>
    );
  }

  if (quiz.status !== "PUBLISHED") {
    return (
      <section className="qp-content">
        <h1>Editing unavailable</h1>
        <p>This quiz is not currently published.</p>
        <Link to="/app/dashboard/present">
          Back to dashboard
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
      key={`${quiz.quiz_id}:${quiz.version.quiz_version_id}`}
      initialEditor={initialEditor}
      existingQuiz={quiz}
      onReload={resource.reload}
    />
  );
}
