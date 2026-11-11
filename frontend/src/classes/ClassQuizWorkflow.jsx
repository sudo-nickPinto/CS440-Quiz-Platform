import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router";

import { useAccount } from "../authenticated-demo/account";
import { useAction, useApi } from "../authenticated-demo/rest";
import RequestError from "../authenticated-demo/RequestError";
import ConfirmDialog from "../authenticated-demo/ConfirmDialog";
import { useConfirm } from "../authenticated-demo/useConfirm";

import { useClassResource } from "./classResources";
import { ResourceMessage } from "./ClassUI";

import {
  canHostApprovedQuiz,
  canSubmitQuiz,
  loadQuizWorkflow,
  paginate,
  submissionMatchesQuiz,
} from "./quizWorkflow";

import "./quiz-workflow.css";
import SubmissionCard from "./SubmissionCard";

function formatDate(value) {
  return value ? new Date(value).toLocaleString() : "—";
}

function Workspace({ classInfo }) {
  const api = useApi();
  const account = useAccount();
  const navigate = useNavigate();
  const action = useAction();
  const confirmer = useConfirm();

  const [revision, setRevision] = useState(0);
  const [result, setResult] = useState({
    key: null,
    data: null,
    error: null,
  });

  const [tab, setTab] = useState("quizzes");
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("ALL");
  const [sort, setSort] = useState("newest");
  const [page, setPage] = useState(1);
  const [notice, setNotice] = useState("");

  const key = `${classInfo.id}:${revision}`;
  const current = result.key === key;

  function reload() {
    setRevision((value) => value + 1);
  }

  useEffect(() => {
    const controller = new AbortController();

    loadQuizWorkflow(api, classInfo.id, controller.signal, classInfo.archived)
      .then((data) => {
        if (!controller.signal.aborted) {
          setResult({ key, data, error: null });
        }
      })
      .catch((error) => {
        if (!controller.signal.aborted) {
          setResult({ key, data: null, error });
        }
      });

    return () => controller.abort();
  }, [api, classInfo.id, classInfo.archived, key]);

  async function mutate(path, options, message) {
    setNotice("");

    const succeeded = await action.run(async () => {
      await api(path, options);
      return true;
    });

    if (succeeded) setNotice(message);

    // Refresh after failures too: another user may have changed the record.
    reload();
  }

  async function submit(quiz) {
    const confirmed = await confirmer.confirm({
      label: "Submit quiz",
      title: `Submit ${quiz.version.title}?`,
      message:
        `Version ${quiz.version.version_number} will be sent ` +
        "to the class organizers for approval.",
      confirmLabel: "Submit",
    });

    if (!confirmed) return;

    await mutate(
      `/classes/${classInfo.id}/quiz-submissions`,
      {
        method: "POST",
        body: JSON.stringify({
          quiz_version_id: quiz.version.quiz_version_id,
        }),
      },
      "Quiz version submitted for approval.",
    );
  }

  async function decide(submission, nextStatus) {
    const approving = nextStatus === "APPROVED";

    const confirmed = await confirmer.confirm({
      label: approving ? "Approve submission" : "Reject submission",
      title: approving ? "Approve this version?" : "Reject this submission?",
      message:
        `This decision applies to version ID ` +
        `${submission.quiz_version_id}, not future edits.`,
      confirmLabel: approving ? "Approve" : "Reject",
    });

    if (!confirmed) return;

    await mutate(
      `/classes/${classInfo.id}/quiz-submissions/${submission.submission_id}`,
      {
        method: "PATCH",
        body: JSON.stringify({ status: nextStatus }),
      },
      approving ? "Quiz version approved." : "Submission rejected.",
    );
  }

  async function withdraw(submission) {
    const confirmed = await confirmer.confirm({
      label: "Withdraw submission",
      title: "Withdraw this submission?",
      message: "You can submit an eligible published version again later.",
      confirmLabel: "Withdraw",
    });

    if (!confirmed) return;

    await mutate(
      `/classes/${classInfo.id}/quiz-submissions/${submission.submission_id}`,
      { method: "DELETE" },
      "Submission withdrawn.",
    );
  }

  async function host(approved) {
    setNotice("");

    const session = await action.run(() =>
      api(`/classes/${classInfo.id}/quizzes/${approved.quiz_id}/sessions`, {
        method: "POST",
      }),
    );

    if (session) {
      navigate(`/app/host/${session.session_id}`);
    } else {
      reload();
    }
  }

  function selectTab(nextTab) {
    setTab(nextTab);
    setStatus("ALL");
    setPage(1);
  }

  const data = current ? result.data : null;

  const quizByVersion = new Map(
    (data?.quizzes ?? []).map((quiz) => [quiz.version.quiz_version_id, quiz]),
  );

  const source =
    tab === "quizzes"
      ? (data?.quizzes ?? [])
      : tab === "submissions"
        ? (data?.submissions ?? [])
        : (data?.approved ?? []);

  const rows = source.map((item) => {
    if (tab === "quizzes") {
      return {
        item,
        title: item.version.title,
        status: item.status,
        date: item.updated_at,
        id: item.quiz_id,
      };
    }

    if (tab === "submissions") {
      const quiz = quizByVersion.get(item.quiz_version_id);

      return {
        item,
        title: quiz?.version.title ?? `Version ID ${item.quiz_version_id}`,
        status: item.status,
        date: item.submitted_at,
        id: item.submission_id,
      };
    }

    return {
      item,
      title: item.title,
      status: "APPROVED",
      date: item.approved_at,
      id: item.submission_id,
    };
  });

  const needle = query.trim().toLowerCase();

  const visible = rows
    .filter(
      (row) =>
        row.title.toLowerCase().includes(needle) &&
        (status === "ALL" || row.status === status),
    )
    .sort((a, b) => {
      if (sort === "title") return a.title.localeCompare(b.title);

      return (
        new Date(b.date ?? 0).getTime() - new Date(a.date ?? 0).getTime() ||
        b.id - a.id
      );
    });

  const paged = paginate(visible, page);

  const statuses =
    tab === "quizzes"
      ? ["DRAFT", "PUBLISHED", "ARCHIVED"]
      : tab === "submissions"
        ? ["PENDING", "APPROVED", "REJECTED", "WITHDRAWN"]
        : ["APPROVED"];

  return (
    <section className="cl-page qw">
      <ConfirmDialog confirmer={confirmer} />

      <div className="cl-classbar">
        <Link
          className="cl-button cl-secondary"
          to={`/app/classes/${classInfo.id}`}
        >
          ← Class
        </Link>

        <div>
          <h1>{classInfo.name}: Quizzes</h1>
          <p>Publish → Submit → Organizer approval → Host</p>
        </div>

        {!classInfo.archived && (
          <Link
            className="cl-button"
            to={`/app/quizzes/new?class=${classInfo.id}`}
          >
            + New quiz
          </Link>
        )}
      </div>

      {classInfo.archived && (
        <p className="qw-message">
          This class is archived. Creating, submitting, and hosting quizzes are
          unavailable.
        </p>
      )}

      <div className="qw-tabs" role="group" aria-label="Quiz sections">
        <button
          type="button"
          aria-pressed={tab === "quizzes"}
          onClick={() => selectTab("quizzes")}
        >
          {classInfo.canManage ? "Class quizzes" : "My quizzes"}
        </button>

        <button
          type="button"
          aria-pressed={tab === "submissions"}
          onClick={() => selectTab("submissions")}
        >
          {classInfo.canManage ? "Review submissions" : "My submissions"}
        </button>

        <button
          type="button"
          aria-pressed={tab === "approved"}
          onClick={() => selectTab("approved")}
        >
          Approved quizzes
        </button>

        <button type="button" disabled={action.busy} onClick={reload}>
          Refresh
        </button>
      </div>

      <div className="qw-toolbar">
        <label>
          Search
          <input
            type="search"
            value={query}
            onChange={(event) => {
              setQuery(event.target.value);
              setPage(1);
            }}
            placeholder="Search quizzes or version IDs…"
          />
        </label>

        <label>
          Status
          <select
            value={status}
            onChange={(event) => {
              setStatus(event.target.value);
              setPage(1);
            }}
          >
            <option value="ALL">All statuses</option>
            {statuses.map((value) => (
              <option key={value} value={value}>
                {value}
              </option>
            ))}
          </select>
        </label>

        <label>
          Sort
          <select
            value={sort}
            onChange={(event) => {
              setSort(event.target.value);
              setPage(1);
            }}
          >
            <option value="newest">Newest first</option>
            <option value="title">Title A–Z</option>
          </select>
        </label>
      </div>

      <RequestError error={action.error} />

      {notice && (
        <p className="qw-message" role="status">
          {notice}
        </p>
      )}

      {!current ? (
        <p className="qw-message" role="status">
          Loading quizzes…
        </p>
      ) : result.error ? (
        <RequestError error={result.error} retry={reload} />
      ) : (
        <>
          <p className="qw-message" aria-live="polite">
            {visible.length} matching {visible.length === 1 ? "item" : "items"}
          </p>

          {visible.length === 0 ? (
            <div className="qw-message">
              <h2>No matching items</h2>
              <p>
                {tab === "quizzes"
                  ? "Create a quiz, or ask its owner to share it with you."
                  : tab === "submissions"
                    ? "Open a published quiz in the quiz list to submit it."
                    : "Approved current versions appear here after organizer review."}
              </p>
            </div>
          ) : (
            <div className="qw-grid">
              {paged.items.map(({ item, title, status: rowStatus }) => {
                if (tab === "quizzes") {
                  const records = data.submissions.filter((submission) =>
                    submissionMatchesQuiz(submission, item),
                  );

                  const approved = data.approved.some(
                    (entry) =>
                      entry.quiz_version_id === item.version.quiz_version_id,
                  );

                  const pending = records.some(
                    (entry) => entry.status === "PENDING",
                  );

                  const eligible = canSubmitQuiz(item);

                  return (
                    <article className="qw-card" key={item.quiz_id}>
                      <span className="qw-badge">{rowStatus}</span>
                      <h2>{title}</h2>

                      <p>
                        Version {item.version.version_number} ·{" "}
                        {item.version.questions.length} questions
                      </p>

                      <p>Created by {item.author_name}</p>

                      <p>
                        {approved
                          ? "This version is approved."
                          : pending
                            ? "Your submission is awaiting review."
                            : eligible
                              ? "Published; approval is required before hosting."
                              : "Publish the draft before submitting it."}
                      </p>

                      <div className="qw-actions">
                        <Link
                          to={`/app/quizzes/${item.quiz_id}`}
                          state={{ classId: classInfo.id }}
                        >
                          View quiz
                        </Link>

                        {item.can_edit &&
                          item.status !== "ARCHIVED" &&
                          !classInfo.archived && (
                            <Link
                              to={`/app/quizzes/${item.quiz_id}/edit`}
                              state={{ classId: classInfo.id }}
                            >
                              Edit quiz
                            </Link>
                          )}

                        {eligible && !approved && !pending && (
                          <button
                            type="button"
                            disabled={action.busy || classInfo.archived}
                            onClick={() => void submit(item)}
                          >
                            Submit for approval
                          </button>
                        )}
                      </div>
                    </article>
                  );
                }

                if (tab === "submissions") {
                  return (
                    <SubmissionCard
                      key={item.submission_id}
                      submission={item}
                      classInfo={classInfo}
                      accountId={account.account_id}
                      busy={action.busy}
                      onDecide={(submission, nextStatus) =>
                        void decide(submission, nextStatus)
                      }
                      onWithdraw={(submission) => void withdraw(submission)}
                    />
                  );
                }

                return (
                  <article className="qw-card" key={item.submission_id}>
                    <span className="qw-badge">APPROVED</span>
                    <h2>{title}</h2>
                    <p>Version {item.version_number}</p>
                    <p>Approved: {formatDate(item.approved_at)}</p>

                    {canHostApprovedQuiz(
                      item,
                      account.account_id,
                      classInfo,
                    ) ? (
                      <button
                        type="button"
                        disabled={action.busy}
                        onClick={() => void host(item)}
                      >
                        Host live session
                      </button>
                    ) : (
                      <p>
                        {classInfo.archived
                          ? "Archived classes cannot start sessions."
                          : "The quiz owner or a class organizer can host this quiz."}
                      </p>
                    )}
                  </article>
                );
              })}
            </div>
          )}

          {paged.totalPages > 1 && (
            <nav className="qw-pagination" aria-label="Quiz list pages">
              <button
                type="button"
                disabled={paged.page === 1}
                onClick={() => setPage(paged.page - 1)}
              >
                Previous
              </button>

              <span>
                Page {paged.page} of {paged.totalPages}
              </span>

              <button
                type="button"
                disabled={paged.page === paged.totalPages}
                onClick={() => setPage(paged.page + 1)}
              >
                Next
              </button>
            </nav>
          )}
        </>
      )}
    </section>
  );
}

export default function ClassQuizWorkflow() {
  const { classId } = useParams();
  const resource = useClassResource(classId);

  if (resource.status !== "ready") {
    return <ResourceMessage resource={resource} />;
  }

  return <Workspace key={classId} classInfo={resource.data} />;
}
