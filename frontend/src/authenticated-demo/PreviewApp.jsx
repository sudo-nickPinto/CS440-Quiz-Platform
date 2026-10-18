import { useEffect, useRef } from 'react'
import {
  Link,
  Navigate,
  Route,
  Routes,
  useLocation,
} from 'react-router'
import PreviewDashboard from './PreviewDashboard'
import { QuizEditor, QuizViewer } from './QuizEditor'
import { JoinPage, SessionPage } from './SessionPages'
import { HostResults, ParticipantResults } from './ResultsPages'
import { createInitialState } from './model'
import { dispatch, usePreview } from './store'
import './preview.css'

export default function PreviewApp() {
  const state = usePreview()
  const { pathname } = useLocation()
  const main = useRef(null)

  useEffect(() => {
    main.current?.focus()
    window.scrollTo(0, 0)
  }, [pathname])

  return (
    <div className="qp">
      <a className="qp-skip" href="#preview-main">
        Skip to content
      </a>

      <header className="qp-header">
        <Link className="qp-logo" to="/app/dashboard/present">
          QUIZ<span>.</span>PLATFORM
        </Link>

        <span>Frontend testing</span>

        <button
          onClick={() => {
            if (
              window.confirm(
                'Reset all browser-only preview quizzes and results?',
              )
            ) {
              dispatch({
                type: 'RESET',
                state: createInitialState(),
              })
            }
          }}
        >
          Reset sample data
        </button>
      </header>

      <p className="qp-notice">
        Signed-in frontend test · Quizzes and results use sample data
        saved in this browser. They are not saved to your database or
        separated by signed-in account. Other players are simulated.
      </p>

      {state.storageWarning && (
        <p role="alert">{state.storageWarning}</p>
      )}

      <main
        id="preview-main"
        className="qp-frame"
        ref={main}
        tabIndex={-1}
      >
        <Routes>
          <Route
            path="dashboard/:view"
            element={<PreviewDashboard />}
          />

          <Route path="quizzes/new" element={<QuizEditor />} />
          <Route path="quizzes/:quizId" element={<QuizViewer />} />
          <Route path="join" element={<JoinPage />} />

          <Route
            path="host/:sessionId"
            element={<SessionPage mode="host" />}
          />

          <Route
            path="play/:sessionId"
            element={<SessionPage mode="participant" />}
          />

          <Route
            path="results/host/:sessionId"
            element={<HostResults />}
          />

          <Route
            path="results/me/:sessionId"
            element={<ParticipantResults />}
          />

          <Route
            path="*"
            element={
              <Navigate to="/app/dashboard/present" replace />
            }
          />
        </Routes>
      </main>
    </div>
  )
}