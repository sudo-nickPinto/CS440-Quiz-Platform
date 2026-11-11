import { Link } from "react-router";

import HostQuizButton from "./HostQuizButton";
import { FLOW_STEPS, sendQuizForApproval } from "./quizFlow";
import RequestError from "./RequestError";
import { useAction, useApi } from "./rest";
import "./quiz-flow.css";

function Track({ step }) {
  return (
    <ol className="qf-track">
      {FLOW_STEPS.map((label, index) => {
        const number = index + 1;
        const done = number < step;
        const current = number === step;
        return (
          <li
            key={label}
            className={done ? "is-done" : current ? "is-current" : undefined}
            aria-current={current ? "step" : undefined}
          >
            <span className="qf-mark" aria-hidden="true">
              {done ? "✓" : number}
            </span>
            <span className="qf-label">
              {label}
              {done && <span className="ui-sr"> (done)</span>}
            </span>
          </li>
        );
      })}
    </ol>
  );
}

// The track plus the one button for the next step.
// onChange(message) runs after a successful action, so the page can show the
// message and reload the quiz.
export function QuizFlowPanel({ quiz, flow, onChange }) {
  const api = useApi();
  const action = useAction();

  if (!flow.visible) return null;

  if (flow.error) {
    return (
      <section className="qf" aria-label="Approval status">
        <RequestError error={flow.error} retry={flow.reload} />
      </section>
    );
  }

  if (flow.loading || !flow.state) {
    return (
      <section className="qf" aria-label="Approval status">
        <p className="qf-note" role="status">
          Checking approval status…
        </p>
      </section>
    );
  }

  const { step, action: next, note } = flow.state;

  async function run(work, done) {
    const ok = await action.run(async () => {
      await work();
      return true;
    });
    if (ok) {
      flow.reload();
      onChange?.(done);
    }
  }

  const send = () =>
    run(
      () => sendQuizForApproval(api, quiz.class_id, quiz.quiz_id),
      "Sent for approval.",
    );

  const withdraw = () =>
    run(
      () =>
        api(
          `/classes/${quiz.class_id}/quiz-submissions/${flow.pending.submission_id}`,
          { method: "DELETE" },
        ),
      "Request withdrawn.",
    );

  return (
    <section className="qf" aria-label="Approval status">
      <Track step={step} />

      <div className="qf-next">
        <p className="qf-note">{note}</p>

        {next === "send" && (
          <button
            type="button"
            className="qf-go"
            disabled={action.busy}
            onClick={() => void send()}
          >
            {action.busy ? "Sending…" : "Send for approval"}
          </button>
        )}

        {next === "withdraw" && (
          <button
            type="button"
            className="qf-go is-quiet"
            disabled={action.busy}
            onClick={() => void withdraw()}
          >
            {action.busy ? "Withdrawing…" : "Withdraw request"}
          </button>
        )}

        {next === "review" && (
          <Link
            className="qf-go"
            to={`/app/classes/${quiz.class_id}/submissions/${flow.pending.submission_id}`}
          >
            Review request <span aria-hidden="true">→</span>
          </Link>
        )}

        {next === "host" && (
          <span className="qf-host">
            <HostQuizButton
              quiz={quiz}
              classId={quiz.class_id}
              action={action}
              label="Host live →"
            />
          </span>
        )}
      </div>

      <RequestError error={action.error} />
    </section>
  );
}
