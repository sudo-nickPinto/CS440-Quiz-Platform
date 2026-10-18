import { useState } from "react";
import { Link, useNavigate } from "react-router";

import { useAccount } from "./account";
import { useAction, useApi } from "./rest";
import RequestError from "./RequestError";
import { ResumeSession } from "./SessionPages";

export default function JoinSessionPage() {
  const [code, setCode] = useState("");
  const account = useAccount();
  const api = useApi();
  const action = useAction();
  const navigate = useNavigate();

  async function join(event) {
    event.preventDefault();

    if (!/^\d{6}$/.test(code)) return;

    const joined = await action.run(() =>
      api("/sessions/join", {
        method: "POST",
        body: JSON.stringify({ join_code: code }),
      }),
    );

    if (joined) {
      navigate(`/app/play/${joined.session.session_id}`);
    }
  }

  return (
    <section>
      <div className="ui-titlebar">
        <span>Join a live session</span>
        <span>Participant</span>
      </div>

      <div className="ui-join-page">
        <p className="ui-eyebrow">Participate</p>

        <h1>
          Join a <span className="ui-highlight">live quiz</span>
        </h1>

        <p>Enter the six-digit code on the host’s screen.</p>

        <form onSubmit={join}>
          <fieldset disabled={action.busy}>
            <label htmlFor="session-code">Session code</label>
            <input
              id="session-code"
              className="ui-code-input"
              required
              inputMode="numeric"
              autoComplete="off"
              pattern="[0-9]{6}"
              maxLength={6}
              placeholder="000000"
              value={code}
              onChange={(event) =>
                setCode(event.target.value.replace(/\D/g, "").slice(0, 6))
              }
            />

            <button
              className="qp-primary"
              type="submit"
              disabled={code.length !== 6}
            >
              {action.busy ? "Joining…" : "Join →"}
            </button>
          </fieldset>

          <p>
            Joining as <strong>{account.display_name}</strong>
          </p>
        </form>

        <RequestError error={action.error} />

        {action.error?.code === "session_already_joined" && (
          <p>
            You have already joined this session. Use its previous URL
            or enter its session ID below.
          </p>
        )}

        <Link to="/app/dashboard/participate">
          ← Back to dashboard
        </Link>

        <details className="ui-return">
          <summary>Already joined?</summary>
          <ResumeSession mode="participant" />
        </details>
      </div>
    </section>
  );
}
