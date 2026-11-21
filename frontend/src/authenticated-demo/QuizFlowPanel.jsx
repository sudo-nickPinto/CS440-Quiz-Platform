import { Link } from "react-router";
import { useAccount } from "./account";

import HostQuizButton from "./HostQuizButton";
import { FLOW_STEPS, sendQuizForApproval } from "./quizFlow";
import RequestError from "./RequestError";
import { useApi } from "./rest";
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

// The Draft → Approval → Ready to host timeline, shown in the quiz page's
// strip between the quiz facts and the buttons as one bar split in three.
// The note on what happens next is a tooltip (and read to screen readers).
export function QuizFlowTrack({ flow }) {
  if (!flow.visible) return null;

  if (flow.error) {
    return (
      <div className="qf-inline" aria-label="Approval status">
        <RequestError error={flow.error} retry={flow.reload} />
      </div>
    );
  }

  if (flow.loading || !flow.state) {
    return (
      <div className="qf-inline" aria-label="Approval status">
        <p className="qf-note" role="status">
          Checking approval status…
        </p>
      </div>
    );
  }

  return (
    <div
      className="qf-inline"
      aria-label="Approval status"
      title={flow.state.note}
    >
      <Track step={flow.state.step} />
      <p className="ui-sr">{flow.state.note}</p>
    </div>
  );
}

// The one button for the quiz's next approval step (send, withdraw, review
// or host), at the right end of the quiz page's button row. `action` is the
// page's useAction(), so errors show with the page's other errors.
// onChange() runs after a successful action, so the page can reload the
// quiz.
export function QuizFlowButton({ quiz, flow, action, onChange }) {
  const api = useApi();
  const account = useAccount();

  if (!flow.visible || !flow.state) return null;
  const next = flow.state.action;

  async function run(work) {
    const ok = await action.run(async () => {
      await work();
      return true;
    });
    if (ok) {
      flow.reload();
      onChange?.();
    }
  }

  if (next === "send") {
    return (
      <button
        type="button"
        className="qf-go"
        disabled={action.busy}
        onClick={() =>
          void run(() =>
            sendQuizForApproval(api, quiz.class_id, quiz.quiz_id, account.account_id),
          )
        }
      >
        {action.busy ? "Sending…" : "Send for approval →"}
      </button>
    );
  }

  if (next === "withdraw") {
    return (
      <button
        type="button"
        className="qf-go is-quiet"
        disabled={action.busy}
        onClick={() =>
          void run(
            () =>
              api(
                `/classes/${quiz.class_id}/quiz-submissions/${flow.pending.submission_id}`,
                { method: "DELETE" },
              ),
          )
        }
      >
        {action.busy ? "Withdrawing…" : "Withdraw request"}
      </button>
    );
  }

  if (next === "review") {
    return (
      <Link
        className="qf-go"
        to={`/app/classes/${quiz.class_id}/submissions/${flow.pending.submission_id}`}
      >
        Review request <span aria-hidden="true">→</span>
      </Link>
    );
  }

  if (next === "host") {
    return (
      <span className="qf-host">
        <HostQuizButton
          quiz={quiz}
          classId={quiz.class_id}
          action={action}
          label="Host live →"
        />
      </span>
    );
  }

  return null;
}
