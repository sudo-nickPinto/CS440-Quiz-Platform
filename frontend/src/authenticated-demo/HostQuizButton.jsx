import { useNavigate } from "react-router";

import { hostingState } from "./hosting";
import { useApi } from "./rest";

import "./host-quiz.css";

// Starts a live session for a quiz. Every session belongs to a class, and a
// quiz always lives in exactly one class, so the session is hosted there.
// Lists that don't include class_id (for example approved quizzes) can pass
// classId.
export default function HostQuizButton({
  quiz,
  action,
  classId = quiz.class_id,
  label = "Host live session",
}) {
  const api = useApi();
  const navigate = useNavigate();
  const state = hostingState(quiz, classId);

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

  if (!state.canHost) {
    return (
      <small className="ui-host-blocked" title={state.message}>
        {state.label}
        <span className="ui-host-why"> — {state.message}</span>
      </small>
    );
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
