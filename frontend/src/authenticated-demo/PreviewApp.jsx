import { useEffect, useRef, useState } from "react";
import {
  Link,
  Navigate,
  Route,
  Routes,
  useLocation,
  useNavigationType,
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

import { AccountContext } from "./account";
import { useResource } from "./rest";
import RequestError from "./RequestError";
import PreviewDashboard from "./PreviewDashboard";
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
import { restoreScroll, savedScroll, saveScroll } from "./remember";

// The app restores scroll itself (see below); the browser's own restore
// fights it while pages are still loading.
if (typeof window !== "undefined" && "scrollRestoration" in window.history) {
  window.history.scrollRestoration = "manual";
}

export default function PreviewApp({ onSignOut }) {
  const account = useResource("/me");
  // PATCH /me returns the updated account; use it so the header updates
  // without reloading /me (which would blank the app while it loads).
  const [savedAccount, setSavedAccount] = useState(null);
  const { pathname, key: locationKey } = useLocation();
  const navigationType = useNavigationType();
  const navigate = useNavigate();
  const main = useRef(null);

  // New pages start at the top; Back/Forward returns to where you were.
  // The target is read once per history entry, before anything on the
  // still-loading page can overwrite it.
  const scrollTarget = useRef({ key: null, y: 0 });
  useEffect(() => {
    main.current?.focus({ preventScroll: true });
    if (navigationType === "POP") {
      if (scrollTarget.current.key !== locationKey) {
        scrollTarget.current = { key: locationKey, y: savedScroll(locationKey) };
      }
      return restoreScroll(scrollTarget.current.y);
    }
    window.scrollTo(0, 0);
    return undefined;
    // Only a new page (path) moves the scroll, not ?query changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pathname, account.data]);

  // Keep this history entry's scroll position up to date. A ?query change
  // on the same page (say a tab switch) starts a new entry at the current
  // spot.
  const lastPath = useRef(pathname);
  useEffect(() => {
    if (lastPath.current === pathname) saveScroll(locationKey);
    lastPath.current = pathname;
    let frame = 0;
    // While a link swaps pages the browser can report the old entry being
    // clamped to the top; only record scrolls made on this entry.
    const current = () => (window.history.state?.key ?? "default") === locationKey;
    const onScroll = () => {
      if (!current()) return;
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        if (current()) saveScroll(locationKey);
      });
    };
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener("scroll", onScroll);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [locationKey]);

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
              element={<Navigate to="/app/dashboard/present" replace />}
            />
          </Routes>
        </main>
      </div>
    </AccountContext.Provider>
  );
}
