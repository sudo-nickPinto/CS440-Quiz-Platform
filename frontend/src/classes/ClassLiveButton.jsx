import { useEffect } from "react";
import { useNavigate } from "react-router";

import { useAction, useApi, useResource } from "../authenticated-demo/rest";
import RequestError from "../authenticated-demo/RequestError";

const POLL_MS = 5000;

// Where the game is, so members know what they're walking into
// (docs/CLASS_APPROVAL.md §5).
function liveSubtext(session) {
  if (session.is_host) return "Return to hosting";
  if (session.left) return "You left this session";
  if (session.status === "ACTIVE" && session.current_question_order) {
    return `Join @ Q${session.current_question_order}`;
  }
  return "Join lobby";
}

// The class page's Live button (task 6). Shows one bar per lobby or running
// session in the class; members join without typing the six-digit code.
// Renders nothing while there is no live session or the class is not visible
// to the caller (the endpoint answers 404 for nonmembers).
export default function ClassLiveButton({ classId }) {
  const sessions = useResource(
    classId ? `/classes/${classId}/active-sessions` : null,
    POLL_MS,
  );
  const api = useApi();
  const action = useAction();
  const navigate = useNavigate();
  const { reload } = sessions;

  // Check again as soon as the tab comes back, instead of waiting for a poll.
  useEffect(() => {
    window.addEventListener("focus", reload);
    return () => window.removeEventListener("focus", reload);
  }, [reload]);

  async function open(session) {
    if (session.left) return;
    if (session.is_host) {
      navigate(`/app/host/${session.session_id}`);
      return;
    }
    if (!session.joined) {
      const joined = await action.run(async () => {
        try {
          return await api(`/sessions/${session.session_id}/join`, {
            method: "POST",
          });
        } catch (error) {
          // Joined in another tab since the last poll: go straight in.
          if (error.code === "session_already_joined") return true;
          throw error;
        }
      });
      if (!joined) return;
    }
    navigate(`/app/play/${session.session_id}`);
  }

  if (sessions.error) {
    return (
      <div className="cl-live-list">
        <RequestError error={sessions.error} retry={reload} />
      </div>
    );
  }

  if (!sessions.data?.length) return null;

  return (
    <div className="cl-live-list">
      {sessions.data.map((session) => (
        <button
          key={session.session_id}
          className="cl-live"
          type="button"
          disabled={action.busy || session.left}
          onClick={() => open(session)}
        >
          <span className="cl-live-tag">
            <span className="cl-live-dot" aria-hidden="true" />
            Live
          </span>
          <span className="cl-live-text">
            <strong>{session.quiz_title}</strong>
            <small>{liveSubtext(session)}</small>
          </span>
        </button>
      ))}

      <RequestError error={action.error} />
    </div>
  );
}
