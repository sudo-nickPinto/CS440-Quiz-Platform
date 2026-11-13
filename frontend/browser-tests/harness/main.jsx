// Browser-test entry: the real signed-in app (PreviewApp) with a stand-in
// Auth0 session. Every API call goes to /__test_api, which the Playwright
// fixture answers. This file is only served by `npm run dev:browser-test`;
// the production app has no way to skip sign-in.
import { createRoot } from "react-dom/client";
import { Auth0Context } from "@auth0/auth0-react";
import { BrowserRouter, Route, Routes } from "react-router";

import PreviewApp from "../../src/authenticated-demo/PreviewApp";
import "../../src/index.css";
import "../../src/styles/theme.css";

const auth = {
  isAuthenticated: true,
  isLoading: false,
  getAccessTokenSilently: async () => "browser-test-token",
};

createRoot(document.getElementById("root")).render(
  <Auth0Context.Provider value={auth}>
    <BrowserRouter>
      <Routes>
        <Route path="/app/*" element={<PreviewApp onSignOut={() => {}} />} />
        <Route path="*" element={<h1>Test harness: open an /app/ URL</h1>} />
      </Routes>
    </BrowserRouter>
  </Auth0Context.Provider>,
);
