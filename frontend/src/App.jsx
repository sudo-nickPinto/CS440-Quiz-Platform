import { useEffect, useState } from "react";
import { useAuth0 } from "@auth0/auth0-react";
import { Navigate, Route, Routes, useMatch } from "react-router";

import LandingPage from "./components/LandingPage";
import AuthenticatedDemo from "./authenticated-demo/PreviewApp";
import AccountGate from "./components/AccountGate";
import VerifyEmailConfirmPage from "./components/VerifyEmailConfirmPage";
import { clearExplicitLogin, returnToState, wasExplicitLogin } from "./api";
import "./App.css";

const WAS_SIGNED_IN = "quiz-was-signed-in";
const TRIED = "quiz-silent-tried";

const NO_SESSION = [
  "login_required",
  "consent_required",
  "interaction_required",
  "missing_refresh_token",
  "invalid_grant",
];

export default function App() {
  const {
    isLoading,
    isAuthenticated,
    error,
    user: auth0User,
    loginWithRedirect,
    logout,
  } = useAuth0();

  // True when this page load is the return from a Sign in / Create account
  // click (not the silent check), read once before the flag is cleared.
  const [afterExplicitLogin] = useState(wasExplicitLogin);

  // The page the verification email links to. It is public and must not
  // redirect anywhere on its own, so it skips the session restore below and
  // is rendered before the signed-in/signed-out branches.
  const onVerifyEmailPage = useMatch("/verify-email") !== null;

  // Manage session restoration. Do not return JSX from this effect.
  useEffect(() => {
    if (isLoading || onVerifyEmailPage) return;

    // The flag only describes the redirect that led to this page load.
    clearExplicitLogin();

    try {
      if (isAuthenticated) {
        localStorage.setItem(WAS_SIGNED_IN, "1");
        sessionStorage.removeItem(TRIED);
        return;
      }

      if (error) {
        localStorage.removeItem(WAS_SIGNED_IN);
        sessionStorage.removeItem(TRIED);
        return;
      }

      const wasSignedIn = localStorage.getItem(WAS_SIGNED_IN);
      const alreadyTried = sessionStorage.getItem(TRIED);

      if (wasSignedIn && !alreadyTried) {
        sessionStorage.setItem(TRIED, "1");

        void loginWithRedirect({
          appState: returnToState(),
          authorizationParams: {
            prompt: "none",
          },
        }).catch(() => {
          try {
            localStorage.removeItem(WAS_SIGNED_IN);
          } catch {
            // Manual sign-in remains available if storage is blocked.
          }
        });
      }
    } catch {
      // Manual sign-in remains available if storage is blocked.
    }
  }, [isLoading, isAuthenticated, error, loginWithRedirect, onVerifyEmailPage]);

  function logOut() {
    try {
      localStorage.removeItem(WAS_SIGNED_IN);
      sessionStorage.removeItem(TRIED);
    } catch {
      // Logout can continue without browser storage.
    }

    void logout({
      logoutParams: {
        returnTo: window.location.origin,
      },
    });
  }

  if (onVerifyEmailPage) {
    return <VerifyEmailConfirmPage />;
  }

  if (isLoading) {
    return (
      <main className="lp-app-status">
        <p role="status">Loading your session…</p>
      </main>
    );
  }

  // Render authenticated pages here, outside the effect.
  if (isAuthenticated) {
    return (
      <AccountGate key={auth0User?.sub}>
        <Routes>
          <Route
            path="/app/*"
            element={<AuthenticatedDemo onSignOut={logOut} />}
          />

          <Route
            path="*"
            element={
              <Navigate
                to="/app/classes"
                replace
              />
            }
          />
        </Routes>
      </AccountGate>
    );
  }

  // A "no session" error from the silent check is expected and stays hidden;
  // after a user-started sign-in it means the sign-in failed, so say so.
  const realError =
    error && (afterExplicitLogin || !NO_SESSION.includes(error.error))
      ? "Sign-in could not be completed. Please select Sign in and try again."
      : "";

  return <LandingPage authError={realError} />;
}
