import { useEffect, useRef } from "react";
import { Link, useNavigate, useParams } from "react-router";

import RequestError from "../authenticated-demo/RequestError";
import { useAction, useApi } from "../authenticated-demo/rest";

// Invite links (/app/join/class/:code) join as soon as the page opens.
export default function JoinClassPage() {
  const { code } = useParams();
  const api = useApi();
  const action = useAction();
  const navigate = useNavigate();
  const started = useRef(false);

  useEffect(() => {
    // Strict Mode mounts twice in development; join only once.
    if (started.current) return;
    started.current = true;

    void (async () => {
      const joined = await action.run(() =>
        api("/classes/join", {
          method: "POST",
          body: JSON.stringify({ code }),
        }),
      );

      if (joined) {
        navigate(`/app/classes/${joined.class_id}`, { replace: true });
      }
    })();
  }, [action, api, code, navigate]);

  return (
    <section className="cl-page" aria-labelledby="join-class-heading">
      <div className="cl-classbar">
        <Link className="cl-button cl-secondary" to="/app/classes">
          ← Classes
        </Link>
      </div>

      <div className="cl-state" role="status">
        <h1 id="join-class-heading">Join a class</h1>

        {!action.error ? (
          <p>Joining…</p>
        ) : action.error.code === "already_class_member" ? (
          <p>You&apos;re already in this class. Find it under Classes.</p>
        ) : null}
      </div>

      {action.error?.code !== "already_class_member" && (
        <RequestError error={action.error} />
      )}
    </section>
  );
}
