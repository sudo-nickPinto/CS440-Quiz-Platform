import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router'
import {
  blankEditor,
  LETTERS,
  newQuestion,
  validateQuiz,
} from './model'
import { dispatch, usePreview } from './store'

export function QuizEditor() {
  const { editor } = usePreview()
  const navigate = useNavigate()
  const [errors, setErrors] = useState([])
  const [reviewing, setReviewing] = useState(false)

  function edit(next) {
    dispatch({ type: 'EDITOR', editor: next })
    setReviewing(false)
  }

  function changeQuestion(id, change) {
    edit({
      ...editor,
      questions: editor.questions.map((q) =>
        q.id === id ? { ...q, ...change } : q,
      ),
    })
  }

  function move(index, offset) {
    const questions = [...editor.questions]

    ;[questions[index], questions[index + offset]] = [
      questions[index + offset],
      questions[index],
    ]

    edit({ ...editor, questions })
  }

  function save() {
    const issues = validateQuiz(editor)
    setErrors(issues)

    if (issues.length) {
      setReviewing(false)
      return
    }

    const id = crypto.randomUUID()

    dispatch({
      type: 'SAVE',
      id,
      nextEditor: blankEditor(),
    })

    navigate(`/app/quizzes/${id}`)
  }

  return (
    <form
      noValidate
      onSubmit={(e) => {
        e.preventDefault()
        const issues = validateQuiz(editor)
        setErrors(issues)
        setReviewing(issues.length === 0)
      }}
    >
      <div className="qp-toolbar">
        <Link to="/app/dashboard/present">← Dashboard</Link>
        <strong>Create a quiz</strong>
        <span>Not saved</span>
      </div>

      <div className="qp-content">
        <p>
          Work in progress is kept only in this browser.
          Saving locks the quiz.
        </p>

        <label>
          Quiz title
          <input
            maxLength={200}
            value={editor.title}
            onChange={(e) =>
              edit({ ...editor, title: e.target.value })
            }
          />
        </label>

        <div className="qp-toolbar">
          <nav className="qp-actions" aria-label="Jump to question">
            {editor.questions.map((q, i) => (
              <a key={q.id} href={`#question-${q.id}`}>
                Q{i + 1}
              </a>
            ))}
          </nav>

          <label>
            Default time (seconds)
            <input
              type="number"
              min="5"
              max="300"
              value={editor.defaultTime}
              onChange={(e) =>
                edit({ ...editor, defaultTime: e.target.value })
              }
            />
          </label>
        </div>

        {editor.questions.map((q, index) => (
          <article
            className="qp-card"
            id={`question-${q.id}`}
            key={q.id}
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
                  disabled={index === editor.questions.length - 1}
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
                          (x) => x.id !== q.id,
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
                  value={q.text}
                  onChange={(e) =>
                    changeQuestion(q.id, { text: e.target.value })
                  }
                />
              </label>

              <fieldset>
                <legend>
                  Choices — select the correct answer
                </legend>

                {q.options.map((option, i) => (
                  <div className="qp-choice-editor" key={i}>
                    <label>
                      <input
                        type="radio"
                        name={`correct-${q.id}`}
                        checked={q.correct === i}
                        onChange={() =>
                          changeQuestion(q.id, { correct: i })
                        }
                      />
                      {LETTERS[i]}
                    </label>

                    <input
                      aria-label={`Question ${index + 1}, choice ${LETTERS[i]}`}
                      maxLength={500}
                      value={option}
                      onChange={(e) =>
                        changeQuestion(q.id, {
                          options: q.options.map((text, j) =>
                            j === i ? e.target.value : text,
                          ),
                        })
                      }
                    />

                    <button
                      type="button"
                      disabled={q.options.length <= 2}
                      aria-label={`Remove choice ${LETTERS[i]}`}
                      onClick={() =>
                        changeQuestion(q.id, {
                          options: q.options.filter(
                            (_, j) => j !== i,
                          ),
                          correct:
                            q.correct === i
                              ? null
                              : q.correct !== null && q.correct > i
                                ? q.correct - 1
                                : q.correct,
                        })
                      }
                    >
                      ×
                    </button>
                  </div>
                ))}

                <button
                  type="button"
                  disabled={q.options.length >= 6}
                  onClick={() =>
                    changeQuestion(q.id, {
                      options: [...q.options, ''],
                    })
                  }
                >
                  + Add choice
                </button>
              </fieldset>

              <label>
                Question time (leave blank to use the default)
                <input
                  type="number"
                  min="5"
                  max="300"
                  value={q.limit ?? ''}
                  placeholder={String(editor.defaultTime)}
                  onChange={(e) =>
                    changeQuestion(q.id, {
                      limit:
                        e.target.value === ''
                          ? null
                          : e.target.value,
                    })
                  }
                />
              </label>
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
          + Add question
        </button>

        {errors.length > 0 && (
          <div className="qp-error" role="alert">
            <strong>Please fix:</strong>
            <ul>
              {errors.map((error) => (
                <li key={error}>{error}</li>
              ))}
            </ul>
          </div>
        )}
      </div>

      <div className="qp-savebar">
        {reviewing ? (
          <>
            <div>
              <strong>Saving is final.</strong>
              <p>
                This preview will mark the quiz public, published,
                and read-only. It is saved only in your browser.
              </p>
            </div>

            <button
              type="button"
              onClick={() => setReviewing(false)}
            >
              Keep editing
            </button>

            <button
              type="button"
              className="qp-primary"
              onClick={save}
            >
              Save for good
            </button>
          </>
        ) : (
          <>
            <span>{editor.questions.length} questions</span>
            <button className="qp-primary" type="submit">
              Review and save
            </button>
          </>
        )}
      </div>
    </form>
  )
}

export function QuizViewer() {
  const { quizId } = useParams()
  const { quizzes } = usePreview()
  const quiz = quizzes.find((q) => q.id === quizId)

  if (!quiz) {
    return (
      <p className="qp-content">
        Quiz not found. Return to the dashboard.
      </p>
    )
  }

  return (
    <section className="qp-content">
      <Link to="/app/dashboard/present">← Dashboard</Link>
      <h1>{quiz.title}</h1>
      <p>
        {quiz.status} · Public · Read-only · Stored in this browser
      </p>

      {quiz.questions.map((q, i) => (
        <article className="qp-card qp-content" key={q.id}>
          <h2>Q{i + 1}. {q.text}</h2>
          <p>{q.limit} seconds</p>

          <ol type="A">
            {q.options.map((text, n) => (
              <li key={n}>
                {text}
                {n === q.correct ? ' — Correct' : ''}
              </li>
            ))}
          </ol>
        </article>
      ))}
    </section>
  )
}