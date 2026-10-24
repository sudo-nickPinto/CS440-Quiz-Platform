import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router";
import { useAccount } from "./account";

import { blankEditor, LETTERS, newQuestion } from "./model";
import { toQuizCreate } from "./quizPayload";
import { useAction, useApi, useResource } from "./rest";
import RequestError from "./RequestError";

export function QuizEditor({
  initialEditor = null,
  existingQuiz = null,
  onReload,
}) {
  const [initial] = useState(() => initialEditor ?? blankEditor());
  const [editor, setEditor] = useState(initial);
  const [reviewing, setReviewing] = useState(false);
  const [validation, setValidation] = useState("");

  const api = useApi();
  const action = useAction();
  const navigate = useNavigate();

  const editing = existingQuiz !== null;
  const dirty = JSON.stringify(editor) !== JSON.stringify(initial);

  const conflict = action.error?.code === "quiz_version_conflict";

  const backTo = editing
    ? `/app/quizzes/${existingQuiz.quiz_id}`
    : "/app/dashboard/present";

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

  function leaveEditor(event) {
    if (action.busy) {
      event.preventDefault();
      return;
    }

    if (dirty && !window.confirm("Discard your unsaved changes?")) {
      event.preventDefault();
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
    <form noValidate onSubmit={review}>
      <fieldset disabled={action.busy} className="qp-form-fields">
        <div className="qp-toolbar">
          <Link to={backTo} onClick={leaveEditor}>
            {editing ? "← Cancel editing" : "← Dashboard"}
          </Link>

          <strong>{editing ? "Edit quiz" : "Create a quiz"}</strong>
        </div>

        <div className="qp-content">
          <p>
            {editing
              ? "Save changes to publish an updated version. Existing sessions and results keep their original content."
              : "Save to publish your quiz. You can return later to edit it."}
          </p>

          <p>
            Unsaved changes stay on this page only. Leaving without saving
            discards them.
          </p>

          <label>
            Quiz title
            <input
              maxLength={200}
              value={editor.title}
              onChange={(event) =>
                edit({
                  ...editor,
                  title: event.target.value,
                })
              }
            />
          </label>

          <label>
            Description (optional)
            <textarea
              rows={3}
              value={editor.description ?? ""}
              onChange={(event) =>
                edit({
                  ...editor,
                  description: event.target.value,
                })
              }
            />
          </label>

          <label>
            Default time (seconds)
            <input
              type="number"
              min={1}
              max={65535}
              step={1}
              value={editor.defaultTime}
              onChange={(event) =>
                edit({
                  ...editor,
                  defaultTime: event.target.value,
                })
              }
            />
          </label>

          {editor.questions.map((question, index) => (
            <article className="qp-card" key={question.id}>
              <div className="qp-bar">
                <strong>Question {index + 1}</strong>

                <div className="qp-actions">
                  <button
                    type="button"
                    disabled={index === 0}
                    aria-label={`Move question ${index + 1} up`}
                    onClick={() => move(index, -1)}
                  >
                    ↑
                  </button>

                  <button
                    type="button"
                    disabled={index === editor.questions.length - 1}
                    aria-label={`Move question ${index + 1} down`}
                    onClick={() => move(index, 1)}
                  >
                    ↓
                  </button>

                  <button
                    type="button"
                    onClick={() => {
                      if (window.confirm("Delete this question?")) {
                        edit({
                          ...editor,
                          questions: editor.questions.filter(
                            (item) => item.id !== question.id,
                          ),
                        });
                      }
                    }}
                  >
                    Delete
                  </button>
                </div>
              </div>

              <div className="qp-content">
                <label>
                  Question text
                  <textarea
                    rows={2}
                    value={question.text}
                    onChange={(event) =>
                      changeQuestion(question.id, {
                        text: event.target.value,
                      })
                    }
                  />
                </label>

                <fieldset>
                  <legend>Choices — select the correct answer</legend>

                  {question.options.map((option, choiceIndex) => (
                    <div className="qp-choice-editor" key={choiceIndex}>
                      <label>
                        <input
                          type="radio"
                          name={`correct-${question.id}`}
                          checked={question.correct === choiceIndex}
                          onChange={() =>
                            changeQuestion(question.id, {
                              correct: choiceIndex,
                            })
                          }
                        />
                        {LETTERS[choiceIndex]}
                      </label>

                      <input
                        maxLength={500}
                        value={option}
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

                      <button
                        type="button"
                        disabled={question.options.length <= 2}
                        aria-label={`Remove choice ${LETTERS[choiceIndex]}`}
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
                    </div>
                  ))}

                  <button
                    type="button"
                    disabled={question.options.length >= 4}
                    onClick={() =>
                      changeQuestion(question.id, {
                        options: [...question.options, ""],
                      })
                    }
                  >
                    ＋ Add choice
                  </button>
                </fieldset>

                <label>
                  Answer explanation (optional)
                  <textarea
                    rows={4}
                    maxLength={5000}
                    value={question.explanation ?? ""}
                    placeholder="Explain why the selected answer is correct."
                    aria-describedby={`explanation-help-${question.id}`}
                    onChange={(event) =>
                      changeQuestion(question.id, {
                        explanation: event.target.value,
                      })
                    }
                  />
                </label>

                <small id={`explanation-help-${question.id}`}>
                  Explain the reasoning, show a calculation, or add a useful
                  example. This is saved with the quiz and available in the
                  final results review.{" "}
                  {(question.explanation ?? "").length.toLocaleString()}
                  /5,000 characters.
                </small>

                <label>
                  Question time (blank uses default)
                  <input
                    type="number"
                    min={1}
                    max={65535}
                    step={1}
                    value={question.limit ?? ""}
                    placeholder={String(editor.defaultTime)}
                    onChange={(event) =>
                      changeQuestion(question.id, {
                        limit:
                          event.target.value === "" ? null : event.target.value,
                      })
                    }
                  />
                </label>

                <label>
                  Base points
                  <input
                    type="number"
                    min={1}
                    max={4294967295}
                    step={1}
                    value={question.basePoints ?? 1000}
                    onChange={(event) =>
                      changeQuestion(question.id, {
                        basePoints: event.target.value,
                      })
                    }
                  />
                </label>

                <p>The server calculates the awarded score.</p>
              </div>
            </article>
          ))}

          <button
            type="button"
            onClick={() =>
              edit({
                ...editor,
                questions: [...editor.questions, newQuestion()],
              })
            }
          >
            ＋ Add question
          </button>

          {validation && (
            <p className="qp-error" role="alert">
              {validation}
            </p>
          )}
        </div>

        <div className="qp-savebar">
          {reviewing ? (
            <>
              <p>
                {editing
                  ? "Publish these changes for future sessions?"
                  : "Publish this quiz?"}
              </p>

              <button type="button" onClick={() => setReviewing(false)}>
                Keep editing
              </button>

              <button
                type="button"
                className="qp-primary"
                disabled={conflict}
                onClick={() => void save()}
              >
                {action.busy
                  ? "Saving…"
                  : editing
                    ? "Save changes"
                    : "Publish quiz"}
              </button>
            </>
          ) : (
            <button type="submit" className="qp-primary" disabled={conflict}>
              Review and save
            </button>
          )}
        </div>
      </fieldset>

      <RequestError error={action.error} />

      {conflict && (
        <div className="qp-content">
          <p>
            Your edits are still on this page. Copy anything you want to keep
            before loading the latest saved version.
          </p>

          <button
            type="button"
            disabled={action.busy}
            onClick={() => {
              if (
                window.confirm(
                  "Discard the changes on this page and load the latest version?",
                )
              ) {
                onReload?.();
              }
            }}
          >
            Reload latest version
          </button>
        </div>
      )}
    </form>
  );
}

export function QuizViewer() {
  const { quizId } = useParams();
  const account = useAccount();
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

  return (
    <section className="qp-content">
      <Link to="/app/dashboard/present">← Dashboard</Link>

      <h1>{quiz.version.title}</h1>
      <p>
        {quiz.status} · {quiz.visibility} · Version{" "}
        {quiz.version.version_number}
      </p>

      {quiz.status === "PUBLISHED" && quiz.author_id === account.account_id && (
        <Link
          className="qp-button qp-primary"
          to={`/app/quizzes/${quiz.quiz_id}/edit`}
        >
          Edit quiz
        </Link>
      )}

      {quiz.version.questions.map((question, index) => (
        <article className="qp-card qp-content" key={question.question_id}>
          <h2>
            Q{index + 1}. {question.question_text}
          </h2>

          <p>
            {question.time_limit_seconds} seconds · {question.base_points} base
            points
          </p>

          <ol type="A">
            {question.choices.map((choice) => (
              <li key={choice.choice_id}>
                {choice.choice_text}
                {choice.is_correct ? " — Correct" : ""}
              </li>
            ))}
          </ol>
          <div className="qp-explanation">
            <h3>Answer explanation</h3>
            <p>{question.explanation || "No explanation was provided."}</p>
          </div>
        </article>
      ))}
    </section>
  );
}
