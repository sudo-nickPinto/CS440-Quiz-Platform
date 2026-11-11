import { useEffect, useRef, useState } from "react";
import {
  Link,
  Navigate,
  Route,
  Routes,
  useLocation,
  useNavigate,
} from "react-router";
import Avatar from "../avatars/Avatar";
import ClassesPage from "../classes/ClassesPage";
import ClassPage from "../classes/ClassPage";
import JoinClassPage from "../classes/JoinClassPage";
import SubmissionPreviewPage from "../classes/SubmissionPreview";
import QuizBurgLogo from "../classes/QuizBurgLogo";
import {
  ClassSessionReportPage,
  ClassQuizReportPage,
  ClassStudentReportPage,
} from "../classes/ClassReports";

import AppNav from "./AppNav";
import { AccountContext } from "./account";
import { useResource } from "./rest";
import RequestError from "./RequestError";
import { QuizEditor, QuizViewer } from "./QuizEditor";
import { QuizHostingHistory } from "./QuizHistory";
import JoinSessionPage from "./JoinSessionPage";
import ProfilePage from "./ProfilePage";
import LiveSessionPage from "./LiveSessionPage";
import EditQuizPage from "./EditQuizPage";
import "./preview.css";
import SessionResults from "./SessionResults";
import "./taha-ui.css";
import "../classes/classes.css";
import "./quizburg-polish.css";
// After the polish sheet: the class page's Students tab, status rows and
// Add member pop-up (class-admin-main.html / made-dashboard-main.html).
import "../classes/class-admin.css";
import "./dismissPopovers.js";

export default function PreviewApp({ onSignOut }) {
  const account = useResource("/me");
  // PATCH /me returns the updated account; use it so the header updates
  // without reloading /me (which would blank the app while it loads).
  const [savedAccount, setSavedAccount] = useState(null);
  const { pathname } = useLocation();
  const navigate = useNavigate();
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

  const me = savedAccount ?? account.data;

  if (!me?.is_active) {
    return (
      <p role="alert">This account is inactive. Contact your administrator.</p>
    );
  }

  return (
    <AccountContext.Provider value={me}>
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

          <AppNav pathname={pathname} />

          <div className="ui-user">
            <span className="ui-user-name">{me.display_name}</span>

            <details className="qb-account">
              <summary
                className="ui-avatar"
                aria-label={`Account menu for ${me.display_name}`}
              >
                <Avatar avatarKey={me.avatar_key} name={me.display_name} />
              </summary>

              <div className="qb-account-menu">
                <p>
                  <small>Signed in as</small>
                  <strong>{me.display_name}</strong>
                </p>
                <button type="button" onClick={() => navigate("/app/profile")}>
                  Edit profile
                </button>
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
              path="classes/:classId/submissions/:submissionId"
              element={<SubmissionPreviewPage key={pathname} />}
            />

            <Route
              path="classes/:classId/students/:accountId/report"
              element={<ClassStudentReportPage key={pathname} />}
            />

            {/* The global dashboard was folded into the class pages; old links
                land on the class list. */}
            <Route
              path="dashboard/*"
              element={<Navigate to="/app/classes" replace />}
            />

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
              path="profile"
              element={<ProfilePage onSaved={setSavedAccount} />}
            />

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
              element={<Navigate to="/app/classes" replace />}
            />
          </Routes>
        </main>
      </div>
    </AccountContext.Provider>
  );
}
