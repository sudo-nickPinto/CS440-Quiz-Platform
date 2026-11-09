import { useNavigate } from "react-router";

import { useApi } from "./rest";

// Starts a live session for a quiz. Every session belongs to a class, and a
// quiz always lives in exactly one class, so the session is hosted there.
// The backend also checks that this quiz version is approved for the class.
export default function HostQuizButton({
  quiz,
  action,
  label = "Host live session",
}) {
  const api = useApi();
  const navigate = useNavigate();
  const classId = quiz.class_id;

  async function host() {
    const session = await action.run(() =>
      api(`/classes/${classId}/quizzes/${quiz.quiz_id}/sessions`, {
        method: "POST",
      }),
    );

    if (session) {
      navigate(`/app/host/${session.session_id}`);
    }
  }

  if (!classId) {
    // Old quizzes from before classes can't be hosted any more.
    return <small>Not in a class</small>;
  }

  return (
    <button
      type="button"
      disabled={action.busy}
      onClick={() => void host()}
    >
      {label}
    </button>
  );
}
