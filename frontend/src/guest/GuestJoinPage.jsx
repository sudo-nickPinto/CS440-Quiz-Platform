// Guest join for the capstone live demo (temporary, demo branch only):
// game code, then nickname, then straight into the lobby.
import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router";

import QuizBurgLogo from "../classes/QuizBurgLogo";
import { guestPost, setGuestToken } from "./guestSession";
import "./guest-join.css";

const NICKNAME_MAX = 30;

export default function GuestJoinPage() {
  const navigate = useNavigate();
  const [step, setStep] = useState("code");
  const [code, setCode] = useState("");
  const [game, setGame] = useState(null);
  const [nickname, setNickname] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const input = useRef(null);

  useEffect(() => {
    input.current?.focus();
  }, [step]);

  async function checkCode(event) {
    event.preventDefault();
    if (!/^\d{6}$/.test(code) || busy) return;
    setBusy(true);
    setError("");
    try {
      setGame(await guestPost("/check-code", { join_code: code }));
      setStep("nickname");
    } catch (failure) {
      setError(
        failure.code === "join_code_not_found"
          ? "No game is using that code. Check the code on the big screen."
          : failure.message,
      );
    } finally {
      setBusy(false);
    }
  }

  async function join(event) {
    event.preventDefault();
    const name = nickname.trim();
    if (!name || busy) return;
    setBusy(true);
    setError("");
    try {
      const joined = await guestPost("/join", {
        join_code: code,
        nickname: name,
      });
      setGuestToken(joined.guest_token, joined.session.session_id);
      navigate(`/app/play/${joined.session.session_id}`, { replace: true });
    } catch (failure) {
      if (failure.code === "join_code_not_found") {
        setStep("code");
        setError("That game has ended or is no longer taking players.");
      } else {
        setError(failure.message);
      }
      setBusy(false);
    }
  }

  return (
    <div className="gj">
      <header className="gj-header">
        <Link className="qb-brand-link" to="/" aria-label="QuizBurg — Home">
          <QuizBurgLogo />
        </Link>
      </header>

      <main className="gj-main">
        <section className="gj-card" aria-labelledby="gj-title">
          {step === "code" ? (
            <form onSubmit={checkCode} noValidate>
              <p className="gj-eyebrow">Step 1 of 2</p>
              <h1 id="gj-title">Enter the game code</h1>
              <p className="gj-help">
                It&apos;s the six-digit code on the host&apos;s screen.
              </p>

              <label className="gj-label" htmlFor="gj-code">
                Game code
              </label>
              <input
                id="gj-code"
                ref={input}
                className="gj-input gj-code"
                inputMode="numeric"
                autoComplete="off"
                maxLength={6}
                placeholder="000000"
                value={code}
                disabled={busy}
                onChange={(event) => {
                  setCode(event.target.value.replace(/\D/g, "").slice(0, 6));
                  setError("");
                }}
              />

              <button
                className="gj-button"
                type="submit"
                disabled={busy || code.length !== 6}
              >
                {busy ? "Checking…" : "Next →"}
              </button>
            </form>
          ) : (
            <form onSubmit={join} noValidate>
              <p className="gj-eyebrow">Step 2 of 2</p>
              <h1 id="gj-title">Pick a nickname</h1>
              <p className="gj-help">
                Joining <strong>{game?.quiz_title || "the game"}</strong>.
                Everyone in the room will see this name.
              </p>

              <label className="gj-label" htmlFor="gj-nickname">
                Nickname
              </label>
              <input
                id="gj-nickname"
                ref={input}
                className="gj-input"
                autoComplete="nickname"
                maxLength={NICKNAME_MAX}
                placeholder="e.g. QuizWhiz"
                value={nickname}
                disabled={busy}
                onChange={(event) => {
                  setNickname(event.target.value);
                  setError("");
                }}
              />

              <button
                className="gj-button"
                type="submit"
                disabled={busy || !nickname.trim()}
              >
                {busy ? "Joining…" : "Join game →"}
              </button>

              <button
                className="gj-back"
                type="button"
                disabled={busy}
                onClick={() => {
                  setStep("code");
                  setError("");
                }}
              >
                ← Use a different code
              </button>
            </form>
          )}

          {error && (
            <p className="gj-error" role="alert">
              {error}
            </p>
          )}
        </section>
      </main>
    </div>
  );
}
