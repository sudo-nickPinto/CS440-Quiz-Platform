import { useState } from 'react'
import {
  Link,
  useNavigate,
  useParams,
} from 'react-router'

import {
  blankEditor,
  LETTERS,
  newQuestion,
} from './model'
import { toQuizCreate } from './quizPayload'
import { useAction, useApi, useResource } from './rest'
import RequestError from './RequestError'

export function QuizEditor() {
  const [editor, setEditor] = useState(blankEditor)
  const [reviewing, setReviewing] = useState(false)
  const [validation, setValidation] = useState('')

  const api = useApi()
  const action = useAction()
  const navigate = useNavigate()

  function edit(next) {
    setEditor(next)
    setReviewing(false)
    setValidation('')
  }

  function changeQuestion(id, changes) {
    edit({
      ...editor,
      questions: editor.questions.map((question) =>
        question.id === id
          ? { ...question, ...changes }
          : question,
      ),
    })
  }

  function move(index, offset) {
    const questions = [...editor.questions]
    const next = index + offset

    ;[questions[index], questions[next]] = [
      questions[next],
      questions[index],
    ]

    edit({ ...editor, questions })
  }

  function review(event) {
    event.preventDefault()

    try {
      toQuizCreate(editor)
      setValidation('')
      setReviewing(true)
    } catch (error) {
      setValidation(error.message)
      setReviewing(false)
    }
  }

  async function save() {
    const quiz = await action.run(() =>
      api('/quizzes', {
        method: 'POST',
        body: JSON.stringify(toQuizCreate(editor)),
      }),
    )

    if (quiz) {
      navigate(`/app/quizzes/${quiz.quiz_id}`, {
        replace: true,
      })
    }
  }

  return (
    <form noValidate onSubmit={review}>
      <fieldset
        disabled={action.busy}
        className="qp-form-fields"
      >
        <div className="qp-toolbar">
          <Link to="/app/dashboard/present">
            ← Dashboard
          </Link>
          <strong>Create a quiz</strong>
        </div>

        <div className="qp-content">
          <p>
            Unsaved work stays on this page only.
            Refreshing or leaving discards it.
            Saving publishes a read-only quiz to the database.
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
            Default time (seconds)
            <input
              type="number"
              min={5}
              max={300}
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
            <article
              className="qp-card"
              key={question.id}
            >
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
                    disabled={
                      index === editor.questions.length - 1
                    }
                    aria-label={`Move question ${index + 1} down`}
                    onClick={() => move(index, 1)}
                  >
                    ↓
                  </button>

                  <button
                    type="button"
                    onClick={() => {
                      if (window.confirm('Delete this question?')) {
                        edit({
                          ...editor,
                          questions: editor.questions.filter(
                            (item) => item.id !== question.id,
                          ),
                        })
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
                  <legend>
                    Choices — select the correct answer
                  </legend>

                  {question.options.map(
                    (option, choiceIndex) => (
                      <div
                        className="qp-choice-editor"
                        key={choiceIndex}
                      >
                        <label>
                          <input
                            type="radio"
                            name={`correct-${question.id}`}
                            checked={
                              question.correct === choiceIndex
                            }
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
                              options: question.options.map(
                                (text, i) =>
                                  i === choiceIndex
                                    ? event.target.value
                                    : text,
                              ),
                            })
                          }
                        />

                        <button
                          type="button"
                          disabled={question.options.length <= 2}
                          aria-label={
                            `Remove choice ${LETTERS[choiceIndex]}`
                          }
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
                    ),
                  )}

                  <button
                    type="button"
                    disabled={question.options.length >= 4}
                    onClick={() =>
                      changeQuestion(question.id, {
                        options: [...question.options, ''],
                      })
                    }
                  >
                    ＋ Add choice
                  </button>
                </fieldset>

                <label>
                  Question time (blank uses default)
                  <input
                    type="number"
                    min={5}
                    max={300}
                    value={question.limit ?? ''}
                    placeholder={String(editor.defaultTime)}
                    onChange={(event) =>
                      changeQuestion(question.id, {
                        limit:
                          event.target.value === ''
                            ? null
                            : event.target.value,
                      })
                    }
                  />
                </label>

                <p>
                  Base points: 1,000. The server calculates
                  the awarded score.
                </p>
              </div>
            </article>
          ))}

          <button
            type="button"
            onClick={() =>
              edit({
                ...editor,
                questions: [
                  ...editor.questions,
                  newQuestion(),
                ],
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
                Saving publishes this quiz.
                It cannot be edited afterward.
              </p>

              <button
                type="button"
                onClick={() => setReviewing(false)}
              >
                Keep editing
              </button>

              <button
                type="button"
                className="qp-primary"
                onClick={() => void save()}
              >
                {action.busy ? 'Saving…' : 'Save for good'}
              </button>
            </>
          ) : (
            <button
              type="submit"
              className="qp-primary"
            >
              Review and save
            </button>
          )}
        </div>
      </fieldset>

      <RequestError error={action.error} />
    </form>
  )
}

export function QuizViewer() {
  const { quizId } = useParams()
  const validId = /^[1-9][0-9]*$/.test(quizId)

  const resource = useResource(
    validId ? `/quizzes/${quizId}` : null,
  )

  if (!validId) {
    return <p role="alert">Invalid quiz ID.</p>
  }

  if (resource.loading) {
    return <p role="status">Loading quiz…</p>
  }

  if (resource.error) {
    return (
      <RequestError
        error={resource.error}
        retry={resource.reload}
      />
    )
  }

  if (!resource.data) return null

  const quiz = resource.data

  return (
    <section className="qp-content">
      <Link to="/app/dashboard/present">
        ← Dashboard
      </Link>

      <h1>{quiz.version.title}</h1>
      <p>
        {quiz.status} · {quiz.visibility} ·
        Read-only · Saved to the database
      </p>

      {quiz.version.questions.map((question, index) => (
        <article
          className="qp-card qp-content"
          key={question.question_id}
        >
          <h2>
            Q{index + 1}. {question.question_text}
          </h2>

          <p>
            {question.time_limit_seconds} seconds ·
            {' '}{question.base_points} base points
          </p>

          <ol type="A">
            {question.choices.map((choice) => (
              <li key={choice.choice_id}>
                {choice.choice_text}
                {choice.is_correct ? ' — Correct' : ''}
              </li>
            ))}
          </ol>
        </article>
      ))}
    </section>
  )
}
