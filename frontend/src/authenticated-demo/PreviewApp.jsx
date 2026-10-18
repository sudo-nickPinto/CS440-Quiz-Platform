import { useEffect, useRef } from "react";
import { Link, Navigate, Route, Routes, useLocation } from "react-router";

import { AccountContext } from "./account";
import { useResource } from "./rest";
import RequestError from "./RequestError";
import PreviewDashboard from "./PreviewDashboard";
import { QuizEditor, QuizViewer } from "./QuizEditor";
import { JoinPage } from "./SessionPages";
import LiveSessionPage from "./LiveSessionPage";
import "./preview.css";

function ResultsPending() {
  return (
    <section className="qp-content">
      <h1>Results are not connected yet</h1>
      <p>
        Live gameplay and saved results will be connected in the next stage.
      </p>
      <Link to="/app/dashboard/present">Return to dashboard</Link>
    </section>
  );
}

export default function PreviewApp() {
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
          <span>{account.data.display_name}</span>
        </header>

        <main id="app-main" className="qp-frame" ref={main} tabIndex={-1}>
          <Routes>
            <Route path="dashboard/:view" element={<PreviewDashboard />} />
            <Route path="quizzes/new" element={<QuizEditor />} />
            <Route
              path="quizzes/:quizId"
              element={<QuizViewer key={pathname} />}
            />
            <Route path="join" element={<JoinPage />} />
            <Route
              path="host/:sessionId"
              element={<LiveSessionPage key={pathname} />}
            />
            <Route
              path="play/:sessionId"
              element={<LiveSessionPage key={pathname} />}
            />
            <Route path="results/*" element={<ResultsPending />} />
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
