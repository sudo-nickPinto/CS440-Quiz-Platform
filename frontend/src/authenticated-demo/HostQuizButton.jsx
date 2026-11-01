import { useState } from "react";
import { useNavigate } from "react-router";

import { useApi } from "./rest";

// Starts a live session for a quiz. With hostClasses (classes the caller may
// host in) it first asks who the session is for: an open session anyone with
// the code can join, or one class whose active members only can join.
// With classId the class is fixed, as on a class page.
export default function HostQuizButton({
  quiz,
  action,
  hostClasses = [],
  hostClassesStatus = "ready",
  hostClassesError = null,
  reloadHostClasses,
  classId = null,
  label = "Host live session",
}) {
  const api = useApi();
  const navigate = useNavigate();
  const [target, setTarget] = useState(classId ? String(classId) : "");
  const choicesReady = Boolean(classId) || hostClassesStatus === "ready";

  async function host() {
    const chosen = target ? Number(target) : null;
    const session = await action.run(() =>
      api(`/quizzes/${quiz.quiz_id}/sessions`, {
        method: "POST",
        // No body keeps the open-session request the backend always accepted.
        ...(chosen ? { body: JSON.stringify({ class_id: chosen }) } : {}),
      }),
    );

    if (session) {
      navigate(`/app/host/${session.session_id}`);
    }
  }

  return (
    <>
      {!classId && (
        <label className="ui-host-for">
          For
          <select
            value={target}
            disabled={!choicesReady || action.busy}
            onChange={(event) => setTarget(event.target.value)}
          >
            <option value="">Open session</option>
            {hostClasses.map((item) => (
              <option key={item.id} value={item.id}>
                {item.name}
              </option>
            ))}
          </select>
        </label>
      )}

      {!classId && hostClassesStatus === "loading" && (
        <small role="status">Loading class choices…</small>
      )}

      {!classId && hostClassesError && (
        <span>
          Could not load class choices.{" "}
          <button type="button" onClick={reloadHostClasses}>
            Retry
          </button>
        </span>
      )}

      <button
        type="button"
        disabled={action.busy || !choicesReady}
        onClick={() => void host()}
      >
        {label}
      </button>
    </>
  );
}
