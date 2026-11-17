import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router";

import RequestError from "../authenticated-demo/RequestError";
import { useAction, useApi } from "../authenticated-demo/rest";

// Invite links (/app/join/class/:code) ask to join as soon as the page
// opens. Usually that is a request an organizer approves; someone invited or
// on the class roster goes straight in.
export default function JoinClassPage() {
  const { code } = useParams();
  const api = useApi();
  const action = useAction();
  const navigate = useNavigate();
  const started = useRef(false);
  const [requested, setRequested] = useState(null);

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

      if (joined?.membership_status === "REQUESTED") {
        setRequested(joined);
      } else if (joined) {
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

        {requested ? (
          <p>
            Request sent to {requested.name}. An organizer needs to accept it;
            you&apos;ll get an email when they do.
          </p>
        ) : !action.error ? (
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
