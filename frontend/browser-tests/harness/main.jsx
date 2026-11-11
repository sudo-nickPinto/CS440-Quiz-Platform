import { createRoot } from "react-dom/client";
import { Auth0Context } from "@auth0/auth0-react";
import { MemoryRouter, Route, Routes } from "react-router";

import { AccountContext } from "../../src/authenticated-demo/account";
import ClassQuizWorkflow from "../../src/classes/ClassQuizWorkflow";

import "../../src/authenticated-demo/preview.css";
import "../../src/authenticated-demo/quizburg-polish.css";
import "../../src/classes/classes.css";

const organizer =
  new URLSearchParams(window.location.search).get("role") === "organizer";

const account = {
  account_id: organizer ? 1 : 2,
  role: organizer ? "ADMIN" : "USER",
  is_active: true,
  display_name: organizer ? "Professor" : "Student",
};

const auth = {
  isAuthenticated: true,
  isLoading: false,
  getAccessTokenSilently: async () => "browser-test-token",
};

createRoot(document.getElementById("root")).render(
  <Auth0Context.Provider value={auth}>
    <AccountContext.Provider value={account}>
      <MemoryRouter initialEntries={["/app/classes/4/quiz-workflow"]}>
        <Routes>
          <Route
            path="/app/classes/:classId/quiz-workflow"
            element={<ClassQuizWorkflow />}
          />

          <Route
            path="/app/host/:sessionId"
            element={<h1>Host route reached</h1>}
          />

          <Route
            path="/app/quizzes/:quizId/edit"
            element={<h1>Editor route reached</h1>}
          />
        </Routes>
      </MemoryRouter>
    </AccountContext.Provider>
  </Auth0Context.Provider>,
);
