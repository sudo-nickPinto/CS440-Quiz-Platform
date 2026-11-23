// Quick host for the capstone live demo (temporary, demo branch only):
// pick one of your quizzes and open its lobby, without going through a class.
// Games start in your own "Live demo (guests)" class, so guests who join
// never land in a real class's roster.
import { useState } from "react";
import { useNavigate } from "react-router";

import { useAction, useApi, useResource } from "../authenticated-demo/rest";
import RequestError from "../authenticated-demo/RequestError";
import "./quick-host.css";

export default function QuickHostPage() {
  const quizzes = useResource("/guest/quick-host/quizzes");
  const api = useApi();
  const action = useAction();
  const navigate = useNavigate();
  const [starting, setStarting] = useState(null);
  const [filter, setFilter] = useState("");

  async function host(quizId) {
    setStarting(quizId);
    const session = await action.run(() =>
      api(`/guest/quick-host/quizzes/${quizId}`, { method: "POST" }),
    );
    if (session) {
      navigate(`/app/host/${session.session_id}`);
    } else {
      setStarting(null);
    }
  }

  const term = filter.trim().toLowerCase();
  const shown = (quizzes.data || []).filter(
    (quiz) =>
      !term ||
      quiz.title.toLowerCase().includes(term) ||
      (quiz.class_name || "").toLowerCase().includes(term),
  );

  return (
    <section className="qh">
      <div className="ui-titlebar">
        <span>Quick host</span>
        <span>Live demo</span>
      </div>

      <div className="qh-body">
        <h1>Host a quiz now</h1>
        <p className="qh-lede">
          Pick a quiz and its lobby opens right away. Anyone can join from the
          home page with the game code and a nickname, with no account or
          class needed.
        </p>

        {quizzes.loading && <p role="status">Loading your quizzes…</p>}
        <RequestError error={quizzes.error} retry={quizzes.reload} />
        <RequestError error={action.error} />

        {quizzes.data && quizzes.data.length === 0 && (
          <p className="qh-empty">
            You have no published quizzes yet. Create and publish one in a
            class first, then it shows up here.
          </p>
        )}

        {quizzes.data && quizzes.data.length > 0 && (
          <>
            <label className="qh-search">
              <span>Search your quizzes</span>
              <input
                type="search"
                value={filter}
                placeholder="Quiz or class name"
                onChange={(event) => setFilter(event.target.value)}
              />
            </label>

            <ul className="qh-list">
              {shown.map((quiz) => (
                <li key={quiz.quiz_id} className="qh-item">
                  <div>
                    <strong>{quiz.title}</strong>
                    <small>
                      {quiz.question_count}{" "}
                      {quiz.question_count === 1 ? "question" : "questions"}
                      {quiz.class_name ? ` · ${quiz.class_name}` : ""}
                    </small>
                  </div>
                  <button
                    type="button"
                    className="qh-host"
                    disabled={starting !== null}
                    onClick={() => host(quiz.quiz_id)}
                  >
                    {starting === quiz.quiz_id ? "Opening…" : "Host now →"}
                  </button>
                </li>
              ))}
              {shown.length === 0 && (
                <li className="qh-empty">No quizzes match “{filter}”.</li>
              )}
            </ul>
          </>
        )}
      </div>
    </section>
  );
}
