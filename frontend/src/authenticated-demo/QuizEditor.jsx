import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router";
import { useAccount } from "./account";

import { blankEditor, LETTERS, newQuestion } from "./model";
import { toQuizCreate } from "./quizPayload";
import { useAction, useApi, useResource } from "./rest";
import RequestError from "./RequestError";
import ConfirmDialog from "./ConfirmDialog";
import { useConfirm } from "./useConfirm";
import { QuestionMenu, TimePicker } from "./EditorParts";

const plural = (count, word) => `${count} ${word}${count === 1 ? "" : "s"}`;

// m:ss, as in the mockup's "6 questions · 3:20 total"
function clock(totalSeconds) {
  const seconds = Number.isFinite(totalSeconds) ? totalSeconds : 0;
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
}

// Scroll a question card under the sticky strip and focus it.
function goToQuestion(id) {
  const card = document.getElementById(`question-${id}`);
  card?.scrollIntoView({ block: "start", behavior: "smooth" });
  card?.focus({ preventScroll: true });
}

// Highlights the jump chip of the card in the upper part of the viewport.
function useCurrentQuestion(ids) {
  const [current, setCurrent] = useState(null);
  const key = ids.join(",");

  useEffect(() => {
    function update() {
      const strip = document.querySelector(".qe-strip");
      const line = (strip?.getBoundingClientRect().bottom ?? 0) + 120;
      let found = ids[0] ?? null;

      for (const id of ids) {
        const card = document.getElementById(`question-${id}`);
        if (card && card.getBoundingClientRect().top <= line) found = id;
      }

      setCurrent(found);
    }

    update();
    window.addEventListener("scroll", update, { passive: true });
    window.addEventListener("resize", update);

    return () => {
      window.removeEventListener("scroll", update);
      window.removeEventListener("resize", update);
    };
    // `key` stands in for the ids array, which is rebuilt every render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  return current;
}

function JumpChips({ ids, current }) {
  return (
    <nav className="qe-jump" aria-label="Jump to question">
      {ids.length ? (
        ids.map((id, index) => (
          <button
            type="button"
            key={id}
            className="qe-jchip"
            aria-current={current === id ? "true" : undefined}
            onClick={() => goToQuestion(id)}
          >
            Q{index + 1}
          </button>
        ))
      ) : (
        <span className="qe-jnone">No questions yet</span>
      )}
    </nav>
  );
}

export function QuizEditor({
  initialEditor = null,
  existingQuiz = null,
  onReload,
}) {
  const [initial] = useState(() => initialEditor ?? blankEditor());
  const [editor, setEditor] = useState(initial);
  const [reviewing, setReviewing] = useState(false);
  const [validation, setValidation] = useState("");
  const [explaining, setExplaining] = useState(() => new Set());

  const api = useApi();
  const action = useAction();
  const navigate = useNavigate();
  const confirmer = useConfirm();

  const editing = existingQuiz !== null;
  const dirty = JSON.stringify(editor) !== JSON.stringify(initial);

  const conflict = action.error?.code === "quiz_version_conflict";

  const backTo = editing
    ? `/app/quizzes/${existingQuiz.quiz_id}`
    : "/app/dashboard/present";

  const ids = editor.questions.map((question) => question.id);
  const current = useCurrentQuestion(ids);

  const defaultTime = Number(editor.defaultTime);
  const ownTime = (question) =>
    question.limit != null && Number(question.limit) !== defaultTime
      ? Number(question.limit)
      : null;
  const timeOf = (question) => Number(question.limit ?? editor.defaultTime);
  // Validation messages start with "Question N:" when one card is at fault.
  const badQuestion =
    ids[Number(/^Question (\d+):/.exec(validation)?.[1]) - 1] ?? null;

  const totalTime = editor.questions.reduce(
    (sum, question) => sum + (timeOf(question) || 0),
    0,
  );

  useEffect(() => {
    if (!dirty) return;

    function warnBeforeUnload(event) {
      event.preventDefault();
      event.returnValue = "";
    }

    window.addEventListener("beforeunload", warnBeforeUnload);

    return () => {
      window.removeEventListener("beforeunload", warnBeforeUnload);
    };
  }, [dirty]);

  async function leaveEditor(event) {
    if (action.busy) {
      event.preventDefault();
      return;
    }

    if (!dirty) return;

    event.preventDefault();

    if (
      await confirmer.confirm({
        label: "Unsaved changes",
        title: "Discard your changes?",
        message: "Leaving now throws away everything you haven't saved.",
        confirmLabel: "Discard",
        cancelLabel: "Keep editing",
      })
    ) {
      navigate(backTo);
    }
  }

  function edit(next) {
    setEditor(next);
    setReviewing(false);
    setValidation("");
  }

  function changeQuestion(id, changes) {
    edit({
      ...editor,
      questions: editor.questions.map((question) =>
        question.id === id ? { ...question, ...changes } : question,
      ),
    });
  }

  function move(index, offset) {
    const questions = [...editor.questions];
    const next = index + offset;

    [questions[index], questions[next]] = [questions[next], questions[index]];

    edit({ ...editor, questions });
  }

  // "+ Insert question here": a blank question at this position.
  function insertAt(index) {
    const question = newQuestion();
    const questions = [...editor.questions];
    questions.splice(index, 0, question);

    edit({ ...editor, questions });

    window.requestAnimationFrame(() => {
      goToQuestion(question.id);
      document.getElementById(`question-text-${question.id}`)?.focus({
        preventScroll: true,
      });
    });
  }

  // Changing the quiz-wide time moves every question that followed it.
  function setQuizTime(seconds) {
    edit({
      ...editor,
      defaultTime: seconds,
      questions: editor.questions.map((question) =>
        ownTime(question) == null ? { ...question, limit: null } : question,
      ),
    });
  }

  // Picking the quiz time for one question means "follow the quiz".
  function setOwnTime(id, seconds) {
    changeQuestion(id, {
      limit: seconds == null || seconds === defaultTime ? null : seconds,
    });
  }

  async function deleteQuestion(question, index) {
    if (
      await confirmer.confirm({
        label: `Question ${index + 1}`,
        title: "Delete this question?",
        message: question.text.trim() || "This question is still blank.",
        confirmLabel: "Delete",
        cancelLabel: "Keep it",
      })
    ) {
      edit({
        ...editor,
        questions: editor.questions.filter((item) => item.id !== question.id),
      });
    }
  }

  function review(event) {
    event.preventDefault();

    try {
      toQuizCreate(editor);
      setValidation("");
      setReviewing(true);
    } catch (error) {
      setValidation(error.message);
      setReviewing(false);
    }
  }

  async function save() {
    if (conflict) return;

    const quiz = await action.run(() => {
      const payload = toQuizCreate(editor);

      if (editing) {
        payload.base_version = existingQuiz.version.version_number;
      }

      return api(editing ? `/quizzes/${existingQuiz.quiz_id}` : "/quizzes", {
        method: editing ? "PUT" : "POST",
        body: JSON.stringify(payload),
      });
    });

    if (quiz) {
      navigate(`/app/quizzes/${quiz.quiz_id}`, {
        replace: true,
      });
    }
  }

  return (
    <form className="qe" noValidate onSubmit={review}>
      <ConfirmDialog confirmer={confirmer} />

      <fieldset disabled={action.busy} className="qp-form-fields">
        <div className="qe-bar">
          <Link className="qe-back" to={backTo} onClick={leaveEditor}>
            <span aria-hidden="true">←</span>
            <span className="qe-back-word">
              {editing ? "Quiz" : "Dashboard"}
            </span>
            <span className="ui-sr">
              {editing ? "Cancel editing" : "Back to dashboard"}
            </span>
          </Link>

          <div className="qe-titlebox">
            <label className="qe-eyebrow" htmlFor="quiz-title">
              Quiz title
            </label>
            <input
              id="quiz-title"
              maxLength={200}
              autoComplete="off"
              placeholder="Untitled quiz"
              value={editor.title}
              onChange={(event) =>
                edit({
                  ...editor,
                  title: event.target.value,
                })
              }
            />

            <textarea
              rows={1}
              className="qe-description"
              aria-label="Description (optional)"
              placeholder="Add a short description (optional)"
              value={editor.description ?? ""}
              onChange={(event) =>
                edit({
                  ...editor,
                  description: event.target.value,
                })
              }
            />
          </div>

          <div className="qe-state">
            <span className={"qe-pill" + (editing ? " is-saved" : "")}>
              {editing
                ? `Editing · v${existingQuiz.version.version_number}`
                : "New quiz"}
            </span>
          </div>
        </div>

        <div className="qe-strip">
          <JumpChips ids={ids} current={current} />

          <TimePicker
            title="Time per question"
            label={`Time per question: ${editor.defaultTime} seconds. Change`}
            defaultTime={editor.defaultTime}
            onPick={setQuizTime}
            summaryClass="qe-tpbtn"
            footer={
              <p className="qe-fine">
                Every question uses this unless you give it its own time.
                The quiz runs <b>{clock(totalTime)}</b>.
              </p>
            }
          >
            <span className="qe-k">
              <span className="qe-long">Time </span>per question
            </span>
            <span className="qe-v">
              <b>{editor.defaultTime}s</b>
              <span aria-hidden="true">▾</span>
            </span>
          </TimePicker>
        </div>

        <div className="qe-stack">
          {editor.questions.length > 0 ? (
            <p className="qe-intro">
              Click a letter to mark the <b>correct answer</b>. Every question
              gets <b>{editor.defaultTime}s</b> unless you give it its own
              time.
            </p>
          ) : (
            <div className="qe-empty">
              <h2>No questions yet.</h2>
              <p>Add one to get started. You need at least one to save.</p>
            </div>
          )}

          {editor.questions.map((question, index) => {
            const own = ownTime(question);
            const showExplanation =
              explaining.has(question.id) || Boolean(question.explanation);

            return (
              <div className="qe-item" key={question.id}>
                {index > 0 && (
                  <div className="qe-insert">
                    <button type="button" onClick={() => insertAt(index)}>
                      + Insert question here
                      <span className="ui-sr"> (before question {index + 1})</span>
                    </button>
                  </div>
                )}

                <article
                  className="qe-card"
                  id={`question-${question.id}`}
                  tabIndex={-1}
                  aria-label={`Question ${index + 1}`}
                >
                  <div className="qe-top">
                    <span>Question {index + 1}</span>

                    <QuestionMenu
                      number={index + 1}
                      first={index === 0}
                      last={index === editor.questions.length - 1}
                      onMove={(offset) => move(index, offset)}
                      onDelete={() => void deleteQuestion(question, index)}
                    />
                  </div>

                  <div className="qe-body">
                    <textarea
                      id={`question-text-${question.id}`}
                      className="qe-qtext"
                      rows={1}
                      aria-label={`Question ${index + 1} text`}
                      placeholder="Type your question"
                      value={question.text}
                      onChange={(event) =>
                        changeQuestion(question.id, {
                          text: event.target.value,
                        })
                      }
                    />

                    <div
                      className="qe-choices"
                      role="radiogroup"
                      aria-label={`Correct answer for question ${index + 1}`}
                    >
                      {question.options.map((option, choiceIndex) => {
                        const correct = question.correct === choiceIndex;

                        return (
                          <div
                            className={"qe-choice" + (correct ? " is-correct" : "")}
                            key={choiceIndex}
                          >
                            <button
                              type="button"
                              className="qe-mark"
                              role="radio"
                              aria-checked={correct}
                              aria-label={`Choice ${LETTERS[choiceIndex]}, mark correct`}
                              title={`Mark ${LETTERS[choiceIndex]} as the correct answer`}
                              onClick={() =>
                                changeQuestion(question.id, {
                                  correct: choiceIndex,
                                })
                              }
                            >
                              <span aria-hidden="true">
                                {correct ? "✓" : LETTERS[choiceIndex]}
                              </span>
                            </button>

                            <input
                              maxLength={500}
                              value={option}
                              placeholder={`Choice ${LETTERS[choiceIndex]}`}
                              aria-label={
                                `Question ${index + 1}, ` +
                                `choice ${LETTERS[choiceIndex]}`
                              }
                              onChange={(event) =>
                                changeQuestion(question.id, {
                                  options: question.options.map((text, i) =>
                                    i === choiceIndex ? event.target.value : text,
                                  ),
                                })
                              }
                            />

                            <span className="qe-choice-end">
                              {correct && (
                                <span className="qe-tag" aria-hidden="true">
                                  Correct
                                </span>
                              )}

                              {question.options.length > 2 && (
                                <button
                                  type="button"
                                  className="qe-rm"
                                  aria-label={`Remove choice ${LETTERS[choiceIndex]}`}
                                  title="Remove choice"
                                  onClick={() =>
                                    changeQuestion(question.id, {
                                      options: question.options.filter(
                                        (_, i) => i !== choiceIndex,
                                      ),
                                      correct:
                                        question.correct === choiceIndex
                                          ? null
                                          : question.correct !== null &&
                                              question.correct > choiceIndex
                                            ? question.correct - 1
                                            : question.correct,
                                    })
                                  }
                                >
                                  ×
                                </button>
                              )}
                            </span>
                          </div>
                        );
                      })}
                    </div>

                    <div className="qe-links">
                      {question.options.length < 4 && (
                        <button
                          type="button"
                          className="ui-linkbtn"
                          onClick={() =>
                            changeQuestion(question.id, {
                              options: [...question.options, ""],
                            })
                          }
                        >
                          + Add choice
                        </button>
                      )}

                      {!showExplanation && (
                        <button
                          type="button"
                          className="ui-linkbtn"
                          onClick={() => {
                            setExplaining(
                              (open) => new Set([...open, question.id]),
                            );
                            window.requestAnimationFrame(() =>
                              document
                                .getElementById(`explanation-${question.id}`)
                                ?.focus(),
                            );
                          }}
                        >
                          + Add explanation
                        </button>
                      )}
                    </div>

                    {showExplanation && (
                      <label className="qe-explanation">
                        <span className="qe-eyebrow">
                          Answer explanation (optional)
                        </span>
                        <textarea
                          id={`explanation-${question.id}`}
                          rows={2}
                          maxLength={5000}
                          value={question.explanation ?? ""}
                          placeholder="Why is this the right answer? Shown in the results review."
                          onChange={(event) =>
                            changeQuestion(question.id, {
                              explanation: event.target.value,
                            })
                          }
                        />
                        <small>
                          {(question.explanation ?? "").length.toLocaleString()}
                          /5,000
                        </small>
                      </label>
                    )}
                  </div>

                  <div className="qe-foot">
                    <span className="qe-eyebrow">Time to answer</span>

                    <TimePicker
                      question
                      title={`Question ${index + 1} time`}
                      label={
                        `Question ${index + 1} time: ${timeOf(question)} seconds, ` +
                        `${own == null ? "quiz default" : "custom"}. Change`
                      }
                      current={own}
                      defaultTime={editor.defaultTime}
                      onPick={(seconds) => setOwnTime(question.id, seconds)}
                      summaryClass={"qe-tchip" + (own == null ? "" : " is-own")}
                    >
                      <b>{timeOf(question)}s</b>
                      <span className="qe-src">
                        {own == null ? "Quiz default" : "Custom"}
                      </span>
                      <span className="qe-car" aria-hidden="true">
                        ▾
                      </span>
                    </TimePicker>

                    {own != null && (
                      <button
                        type="button"
                        className="ui-linkbtn"
                        onClick={() => setOwnTime(question.id, null)}
                      >
                        Reset to default ({editor.defaultTime}s)
                      </button>
                    )}
                  </div>
                </article>
              </div>
            );
          })}

          <button
            type="button"
            className="qe-addq"
            onClick={() =>
              edit({
                ...editor,
                questions: [...editor.questions, newQuestion()],
              })
            }
          >
            <span aria-hidden="true">+</span> Add question
          </button>

          <RequestError error={action.error} />

          {conflict && (
            <div className="qe-conflict">
              <p>
                Your edits are still on this page. Copy anything you want to
                keep before loading the latest saved version.
              </p>

              <button
                type="button"
                className="qb-btn qb-btn-paper"
                disabled={action.busy}
                onClick={async () => {
                  if (
                    await confirmer.confirm({
                      label: "Newer version saved",
                      title: "Load the latest version?",
                      message: "This discards the changes on this page.",
                      confirmLabel: "Load latest",
                      cancelLabel: "Keep my edits",
                    })
                  ) {
                    onReload?.();
                  }
                }}
              >
                Reload latest version
              </button>
            </div>
          )}
        </div>

        <div className={"qe-savebar" + (reviewing ? " is-confirm" : "")}>
          <div className="qe-savebar-in">
            {reviewing ? (
              <>
                <div className="qe-confirm-text">
                  <h2>
                    {editing ? "Publish these changes?" : "Publish this quiz?"}
                  </h2>
                  <p>
                    {editing
                      ? "Future sessions use the new version. Past sessions and results keep their original questions."
                      : "It's published as soon as you save, and you can host it right away. You can still edit it later."}
                  </p>
                </div>

                <div className="qe-confirm-actions">
                  <button
                    type="button"
                    className="qb-btn qb-btn-paper"
                    onClick={() => setReviewing(false)}
                  >
                    Keep editing
                  </button>

                  <button
                    type="button"
                    className="qb-btn"
                    disabled={conflict}
                    onClick={() => void save()}
                  >
                    {action.busy
                      ? "Saving…"
                      : editing
                        ? "Save changes"
                        : "Publish quiz"}
                  </button>
                </div>
              </>
            ) : (
              <>
                <p className="qe-savebar-msg">
                  {validation ? (
                    <>
                      <span className="qe-bad" role="alert">
                        {validation}
                      </span>
                      {badQuestion && (
                        <button
                          type="button"
                          className="ui-linkbtn"
                          onClick={() => goToQuestion(badQuestion)}
                        >
                          Show me
                        </button>
                      )}
                    </>
                  ) : (
                    <>
                      <span>{plural(editor.questions.length, "question")}</span>
                      <span className="qe-dim">{clock(totalTime)} total</span>
                    </>
                  )}
                </p>

                <button type="submit" className="qb-btn" disabled={conflict}>
                  Save quiz
                </button>
              </>
            )}
          </div>
        </div>
      </fieldset>
    </form>
  );
}

export function QuizViewer() {
  const { quizId } = useParams();
  const account = useAccount();
  const api = useApi();
  const action = useAction();
  const navigate = useNavigate();
  const validId = /^[1-9][0-9]*$/.test(quizId);

  const resource = useResource(validId ? `/quizzes/${quizId}` : null);

  if (!validId) {
    return <p role="alert">Invalid quiz ID.</p>;
  }

  if (resource.loading) {
    return <p role="status">Loading quiz…</p>;
  }

  if (resource.error) {
    return <RequestError error={resource.error} retry={resource.reload} />;
  }

  if (!resource.data) return null;

  const quiz = resource.data;
  const mine = quiz.author_id === account.account_id;
  const published = quiz.status === "PUBLISHED";
  const questions = [...quiz.version.questions].sort(
    (a, b) => a.question_order - b.question_order,
  );
  const totalTime = questions.reduce(
    (sum, question) => sum + Number(question.time_limit_seconds || 0),
    0,
  );

  // Same request as "Host live session" on the dashboard.
  async function host() {
    const session = await action.run(() =>
      api(`/quizzes/${quiz.quiz_id}/sessions`, {
        method: "POST",
      }),
    );

    if (session) {
      navigate(`/app/host/${session.session_id}`);
    }
  }

  return (
    <section className="qv" aria-labelledby="quiz-title">
      <div className="qe-bar">
        <Link className="qe-back" to="/app/dashboard/present">
          <span aria-hidden="true">←</span>
          <span className="qe-back-word">Dashboard</span>
          <span className="ui-sr">Back to dashboard</span>
        </Link>

        <div className="qe-titlebox">
          <span className="qe-eyebrow">Quiz</span>
          <h1 id="quiz-title" className="qv-title">
            {quiz.version.title}
          </h1>
          {quiz.version.description && (
            <p className="qv-description">{quiz.version.description}</p>
          )}
        </div>

        <div className="qe-state">
          <span className={"qe-pill" + (published ? " is-saved" : "")}>
            {published ? "Published" : "Archived"} · v
            {quiz.version.version_number}
          </span>
        </div>
      </div>

      <div className="qv-strip">
        <p className="qv-facts">
          <b>{plural(questions.length, "question")}</b>
          <span>{clock(totalTime)} total</span>
          <span>{quiz.visibility === "PUBLIC" ? "Public" : "Private"}</span>
        </p>

        <div className="qv-actions">
          {(mine || account.role === "ADMIN") && (
            <Link
              className="qb-btn qb-btn-paper"
              to={`/app/quizzes/${quiz.quiz_id}/reports`}
            >
              Hosting history
            </Link>
          )}

          {published && mine && (
            <Link
              className="qb-btn qb-btn-paper"
              to={`/app/quizzes/${quiz.quiz_id}/edit`}
            >
              Edit quiz
            </Link>
          )}

          {published && mine && (
            <button
              type="button"
              className="qb-btn"
              disabled={action.busy}
              onClick={() => void host()}
            >
              {action.busy ? "Starting…" : "Host live session →"}
            </button>
          )}
        </div>
      </div>

      <div className="qe-stack">
        <RequestError error={action.error} />

        {questions.map((question, index) => {
          const choices = [...question.choices].sort(
            (a, b) => a.choice_order - b.choice_order,
          );

          return (
            <div className="qe-item" key={question.question_id}>
              {index > 0 && <div className="qv-gap" aria-hidden="true" />}

              <article className="qe-card qv-card">
                <div className="qe-top">
                  <span>Question {index + 1}</span>
                  <span className="qv-time">
                    {question.time_limit_seconds} sec
                  </span>
                </div>

                <div className="qe-body">
                  <h2 className="qv-qtext">{question.question_text}</h2>

                  <ul className="qe-choices" aria-label="Choices">
                    {choices.map((choice, choiceIndex) => (
                      <li
                        key={choice.choice_id}
                        className={
                          "qe-choice" + (choice.is_correct ? " is-correct" : "")
                        }
                      >
                        <span className="qe-mark" aria-hidden="true">
                          {choice.is_correct ? "✓" : LETTERS[choiceIndex]}
                        </span>
                        <span className="qv-ctext">
                          <span className="ui-sr">{LETTERS[choiceIndex]}. </span>
                          {choice.choice_text}
                        </span>
                        <span className="qe-choice-end">
                          {choice.is_correct && (
                            <span className="qe-tag">Correct</span>
                          )}
                        </span>
                      </li>
                    ))}
                  </ul>
                </div>

                <div className="qv-explanation">
                  <span className="qe-eyebrow">Answer explanation</span>
                  <p className={question.explanation ? "" : "qv-none"}>
                    {question.explanation || "No explanation was provided."}
                  </p>
                </div>
              </article>
            </div>
          );
        })}
      </div>
    </section>
  );
}
