import { useEffect, useRef } from "react";
import { Link, Navigate, Route, Routes, useLocation } from "react-router";
import ClassesPage from "../classes/ClassesPage";
import ClassPage from "../classes/ClassPage";
import JoinClassPage from "../classes/JoinClassPage";
import QuizBurgLogo from "../classes/QuizBurgLogo";
import {
  ClassSessionReportPage,
  ClassQuizReportPage,
  ClassStudentReportPage,
} from "../classes/ClassReports";

import { AccountContext } from "./account";
import { useResource } from "./rest";
import RequestError from "./RequestError";
import PreviewDashboard from "./PreviewDashboard";
import { QuizEditor, QuizViewer } from "./QuizEditor";
import { QuizHostingHistory } from "./QuizHistory";
import JoinSessionPage from "./JoinSessionPage";
import LiveSessionPage from "./LiveSessionPage";
import EditQuizPage from "./EditQuizPage";
import "./preview.css";
import SessionResults from "./SessionResults";
import "./taha-ui.css";
import "../classes/classes.css";
import "./quizburg-polish.css";
import "./dismissPopovers.js";

export default function PreviewApp({ onSignOut }) {
  const account = useResource("/me");
  const { pathname } = useLocation();
  const main = useRef(null);

  useEffect(() => {
    main.current?.focus();
    window.scrollTo(0, 0);
  }, [pathname, account.data]);

  if (account.loading) {
    return <p role="status">Loading your account…</p>;
  }

  if (account.error) {
    return <RequestError error={account.error} retry={account.reload} />;
  }

  if (!account.data?.is_active) {
    return (
      <p role="alert">This account is inactive. Contact your administrator.</p>
    );
  }

  return (
    <AccountContext.Provider value={account.data}>
      <div className="qp">
        <a className="qp-skip" href="#app-main">
          Skip to content
        </a>

        <header className="qp-header">
          <Link
            className="qb-brand-link"
            to="/app/classes"
            aria-label="QuizBurg — Classes"
          >
            <QuizBurgLogo />
          </Link>

          <div className="ui-user">
            <span className="ui-user-name">{account.data.display_name}</span>

            <details className="qb-account">
              <summary
                className="ui-avatar"
                aria-label={`Account menu for ${account.data.display_name}`}
              >
                {(account.data.display_name || "User")
                  .trim()
                  .split(/\s+/)
                  .slice(0, 2)
                  .map((part) => part[0])
                  .join("")
                  .toUpperCase()}
              </summary>

              <div className="qb-account-menu">
                <p>
                  <small>Signed in as</small>
                  <strong>{account.data.display_name}</strong>
                </p>
                <button type="button" onClick={onSignOut}>
                  Sign out
                </button>
              </div>
            </details>
          </div>
        </header>

        <main id="app-main" className="qp-frame" ref={main} tabIndex={-1}>
          <Routes>
            <Route path="classes" element={<ClassesPage />} />

            <Route
              path="classes/:classId"
              element={<ClassPage key={pathname} />}
            />

            <Route
              path="classes/:classId/sessions/:sessionId/report"
              element={<ClassSessionReportPage key={pathname} />}
            />

            <Route
              path="classes/:classId/quizzes/:quizId/report"
              element={<ClassQuizReportPage key={pathname} />}
            />

            <Route
              path="classes/:classId/students/:accountId/report"
              element={<ClassStudentReportPage key={pathname} />}
            />

            <Route path="dashboard/:view" element={<PreviewDashboard />} />

            <Route path="quizzes/new" element={<QuizEditor />} />

            <Route
              path="quizzes/:quizId/reports"
              element={<QuizHostingHistory key={pathname} />}
            />

            <Route
              path="quizzes/:quizId/edit"
              element={<EditQuizPage key={pathname} />}
            />

            <Route
              path="quizzes/:quizId"
              element={<QuizViewer key={pathname} />}
            />

            <Route path="join" element={<JoinSessionPage />} />

            <Route
              path="join/class/:code"
              element={<JoinClassPage key={pathname} />}
            />

            <Route
              path="host/:sessionId"
              element={<LiveSessionPage key={pathname} />}
            />

            <Route
              path="play/:sessionId"
              element={<LiveSessionPage key={pathname} />}
            />

            <Route
              path="results/:view/:sessionId"
              element={<SessionResults key={pathname} />}
            />

            <Route
              path="*"
              element={<Navigate to="/app/dashboard/present" replace />}
            />
          </Routes>
        </main>
      </div>
    </AccountContext.Provider>
  );
}
