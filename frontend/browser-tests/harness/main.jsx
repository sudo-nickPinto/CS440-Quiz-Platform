// Browser-test entry: the real signed-in app (PreviewApp) with a stand-in
// Auth0 session. Calls to /__test_api are either mocked by Playwright or
// proxied to the FastAPI test server. This entry exists only in the test build.
import { createRoot } from "react-dom/client";
import { Auth0Context } from "@auth0/auth0-react";
import { BrowserRouter, Route, Routes } from "react-router";

import PreviewApp from "../../src/authenticated-demo/PreviewApp";
import VerifyEmailConfirmPage from "../../src/components/VerifyEmailConfirmPage";
import "../../src/index.css";
import "../../src/styles/theme.css";

const auth = {
  isAuthenticated: true,
  isLoading: false,
  getAccessTokenSilently: async () => window.__quizburgTestToken ?? "browser-test-token",
};

createRoot(document.getElementById("root")).render(
  <Auth0Context.Provider value={auth}>
    <BrowserRouter>
      <Routes>
        <Route path="/verify-email" element={<VerifyEmailConfirmPage />} />
        <Route path="/app/*" element={<PreviewApp onSignOut={() => {}} />} />
        <Route path="*" element={<h1>Test harness: open an /app/ URL</h1>} />
      </Routes>
    </BrowserRouter>
  </Auth0Context.Provider>,
);
