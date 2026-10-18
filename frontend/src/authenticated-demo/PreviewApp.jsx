import { useEffect, useRef } from "react";
import { Link, Navigate, Route, Routes, useLocation } from "react-router";

import { AccountContext } from "./account";
import { useResource } from "./rest";
import RequestError from "./RequestError";
import PreviewDashboard from "./PreviewDashboard";
import { QuizEditor, QuizViewer } from "./QuizEditor";
import JoinSessionPage from "./JoinSessionPage";
import LiveSessionPage from "./LiveSessionPage";
import "./preview.css";
import SessionResults from "./SessionResults";
import "./taha-ui.css";

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
          <Link className="qp-logo" to="/app/dashboard/present">
            QUIZ<span>.</span>PLATFORM
          </Link>

          <div className="ui-user">
            <span className="ui-user-name">{account.data.display_name}</span>

            <span className="ui-avatar" aria-hidden="true">
              {(account.data.display_name || "User")
                .trim()
                .split(/\s+/)
                .slice(0, 2)
                .map((part) => part[0])
                .join("")
                .toUpperCase()}
            </span>

            <button type="button" onClick={onSignOut}>
              Sign out
            </button>
          </div>
        </header>

        <main id="app-main" className="qp-frame" ref={main} tabIndex={-1}>
          <Routes>
            <Route path="dashboard/:view" element={<PreviewDashboard />} />
            <Route path="quizzes/new" element={<QuizEditor />} />
            <Route
              path="quizzes/:quizId"
              element={<QuizViewer key={pathname} />}
            />
            <Route path="join" element={<JoinSessionPage />} />
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
