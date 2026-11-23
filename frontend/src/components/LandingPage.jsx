import { useEffect, useRef, useState } from "react";
import { useAuth0 } from "@auth0/auth0-react";
import { Link } from "react-router";
import {
  PASSWORD_CONNECTION,
  clearExplicitLogin,
  markExplicitLogin,
  returnToState,
} from "../api";
import QuizBurgLogo from "../classes/QuizBurgLogo";
import "./LandingPage.css";

const chapters = [
  {
    id: "build",
    title: "Build",
    heading: "Create it. Check it. Save it.",
    description:
      "Add your questions, answer choices, correct answers, and time limits. Check the complete quiz before saving: saving makes it public and published immediately, and saved quizzes cannot be edited.",
  },
  {
    id: "shared",
    title: "Share",
    heading: "One shared class. Everyone included.",
    description:
      "Everyone with an account belongs to the same shared class. Saved quizzes are public, with no class selection or enrollment step. Create your own quiz to host a session, then share its join code.",
  },
  {
    id: "present",
    title: "Present",
    heading: "Open the lobby. Hit go.",
    description:
      "Host a quiz you created and share the session code. Any signed-in user can join as a participant. Watch the lobby fill up, then start the questions and guide the session.",
  },
  {
    id: "review",
    title: "Review",
    heading: "See how the session went.",
    description:
      "Participants see their own answers, score, and rank. Hosts can view and export results for sessions they hosted, and Admins can access all results. Each session keeps its own results, and saved quizzes stay unchanged.",
  },
];

const sampleParticipants = [
  "AM",
  "NP",
  "UK",
  "PD",
  "TS",
  "JL",
  "RB",
  "KW",
  "EO",
  "MG",
];

function ChapterPreview({ chapter }) {
  if (chapter === "build") {
    return (
      <div className="lp-panel" aria-hidden="true">
        <div className="lp-panel-top">
          <span>Quiz 2 · Recursion Check</span>
          <span>Not saved</span>
        </div>

        <div className="lp-panel-body">
          <div className="lp-field">
            <small>Question 4</small>
            What does a recursive function need to stop?
          </div>

          <div className="lp-option lp-option-correct">
            <i />
            <span>A base case</span>
            <em>correct</em>
          </div>

          <div className="lp-option">
            <i />
            <span>A global variable</span>
          </div>

          <div className="lp-option">
            <i />
            <span>A while loop</span>
          </div>

          <div className="lp-timers">
            {["10s", "20s", "30s", "60s"].map((time) => (
              <span key={time} className={time === "20s" ? "lp-selected" : ""}>
                {time}
              </span>
            ))}
          </div>
        </div>
      </div>
    );
  }

  if (chapter === "shared") {
    return (
      <div className="lp-panel" aria-hidden="true">
        <div className="lp-panel-top">
          <span>Shared quiz library</span>
          <span>Public</span>
        </div>

        <div className="lp-panel-body">
          <div className="lp-class lp-selected">
            One shared class
            <span>Everyone with an account</span>
          </div>

          <div className="lp-field">
            <small>Saved quiz</small>
            Quiz 2 · Recursion Check
          </div>

          <div className="lp-status-row">
            <span className="lp-pill">Public</span>
            <span className="lp-pill lp-selected">Published</span>
            <span className="lp-pill">Read-only</span>
          </div>

          <p className="lp-fine">
            Saving publishes the complete quiz immediately. Saved quizzes cannot
            be edited.
          </p>
        </div>
      </div>
    );
  }

  if (chapter === "present") {
    return (
      <div className="lp-panel" aria-hidden="true">
        <div className="lp-panel-top">
          <span>Lobby · Shared class</span>
          <span>Waiting</span>
        </div>

        <div className="lp-panel-body">
          <div className="lp-session-code">
            <small>Session code</small>
            <b>482193</b>
          </div>

          <div className="lp-joined">
            {Array.from({ length: 16 }, (_, index) => (
              <span key={index} className={index < 10 ? "lp-present" : ""}>
                {sampleParticipants[index] || "·"}
              </span>
            ))}
          </div>

          <div className="lp-go">
            <span>10 participants joined</span>
            <span className="lp-start-example">Start →</span>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="lp-panel" aria-hidden="true">
      <div className="lp-panel-top">
        <span>Results · Recursion Check</span>
        <span>24 played</span>
      </div>

      <div className="lp-panel-body">
        {[12, 11, 10].map((score, index) => (
          <div
            key={score}
            className={`lp-result ${index > 0 ? "lp-result-dim" : ""}`}
          >
            <span className="lp-rank">{index + 1}</span>

            <span className="lp-result-name">
              {index === 0 ? "You" : "Classmate"}
              <small>Sep 22 · Shared class</small>
            </span>

            <span className="lp-score">
              {score}/12
              <i>
                <b style={{ width: `${(score / 12) * 100}%` }} />
              </i>
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

const AUTH_LABELS = {
  login: { idle: "Sign in", busy: "Opening sign-in…" },
  signup: { idle: "Create account", busy: "Opening sign-up…" },
};

// One Sign in / Create account button. Every button is disabled while any
// redirect is pending; only the clicked one says what is happening.
function AuthButton({
  action,
  source,
  pending,
  onStart,
  className,
  shortLabel,
  arrow = false,
}) {
  const isPending = pending?.action === action && pending.source === source;
  const label = AUTH_LABELS[action][isPending ? "busy" : "idle"];

  return (
    <button
      className={className}
      type="button"
      disabled={pending !== null}
      onClick={() => onStart(action, source)}
    >
      {shortLabel ? (
        <>
          <span className="lp-label-long">{label}</span>
          <span className="lp-label-short">
            {isPending ? "Opening…" : shortLabel}
          </span>
        </>
      ) : (
        label
      )}
      {arrow && <span aria-hidden="true">→</span>}
    </button>
  );
}

export default function LandingPage({ authError = "" }) {
  const { loginWithRedirect } = useAuth0();

  // { action: "login" | "signup", source: "header" | "hero" | "cta" }
  const [pending, setPending] = useState(null);
  // { source, message }: shown next to the group that was clicked.
  const [loginError, setLoginError] = useState(null);
  const [activeChapter, setActiveChapter] = useState(0);

  const heroErrorRef = useRef(null);
  const ctaErrorRef = useRef(null);
  const chapterRefs = useRef([]);

  const heroError =
    loginError && loginError.source !== "cta" ? loginError.message : authError;
  const ctaError = loginError?.source === "cta" ? loginError.message : "";

  // Coming back with the browser's Back button can restore this page from
  // the back/forward cache with a redirect still marked as pending.
  useEffect(() => {
    function handlePageShow(event) {
      if (!event.persisted) return;

      clearExplicitLogin();
      setPending(null);
    }

    window.addEventListener("pageshow", handlePageShow);

    return () => {
      window.removeEventListener("pageshow", handlePageShow);
    };
  }, []);

  // Bring a sign-in error into view, e.g. when the header button was used
  // after scrolling away from the hero.
  useEffect(() => {
    if (!loginError) return;

    const reduceMotion = window.matchMedia(
      "(prefers-reduced-motion: reduce)",
    ).matches;
    const target = loginError.source === "cta" ? ctaErrorRef : heroErrorRef;

    target.current?.scrollIntoView({
      behavior: reduceMotion ? "auto" : "smooth",
      block: "nearest",
    });
  }, [loginError]);

  // Track the chapter closest to the middle of the viewport.
  useEffect(() => {
    let frameId = 0;

    function updateActiveChapter() {
      const midpoint = window.innerHeight * 0.5;
      let nextChapter = 0;

      chapterRefs.current.forEach((element, index) => {
        if (element && element.getBoundingClientRect().top < midpoint) {
          nextChapter = index;
        }
      });

      setActiveChapter(nextChapter);
    }

    function scheduleUpdate() {
      window.cancelAnimationFrame(frameId);
      frameId = window.requestAnimationFrame(updateActiveChapter);
    }

    scheduleUpdate();
    window.addEventListener("scroll", scheduleUpdate, { passive: true });
    window.addEventListener("resize", scheduleUpdate);

    return () => {
      window.cancelAnimationFrame(frameId);
      window.removeEventListener("scroll", scheduleUpdate);
      window.removeEventListener("resize", scheduleUpdate);
    };
  }, []);

  async function startLogin(action, source) {
    if (pending) return;

    setLoginError(null);
    setPending({ action, source });

    // Email/password only, so Auth0's hosted page hides its Google button too.
    // Always show the login screen so an existing Auth0 session for a
    // different account isn't reused silently.
    const authorizationParams = {
      connection: PASSWORD_CONNECTION,
      prompt: "login",
    };

    if (action === "signup") {
      authorizationParams.screen_hint = "signup";
    }

    markExplicitLogin();

    try {
      await loginWithRedirect({
        appState: returnToState(),
        authorizationParams,
        // Keep the existing application's back-button behavior.
        openUrl: (url) => window.location.replace(url),
      });
      // The browser is now leaving for Auth0. Keep the buttons disabled so a
      // second click can't start another redirect.
    } catch {
      clearExplicitLogin();
      setPending(null);
      setLoginError({
        source,
        message: "We could not open sign-in. Please try again.",
      });
    }
  }

  const authProps = { pending, onStart: startLogin };

  return (
    <div className="lp">
      <a className="lp-skip" href="#landing-main">
        Skip to content
      </a>

      <header className="lp-header">
        <a
          className="qb-brand-link"
          href="#landing-main"
          aria-label="QuizBurg — Home"
        >
          <QuizBurgLogo />
        </a>

        <nav className="lp-nav" aria-label="Page sections">
          <a href="#how">How it works</a>
          <a href="#who">Who it&apos;s for</a>
        </nav>

        <div
          className="lp-header-actions"
          aria-busy={pending?.source === "header"}
        >
          <AuthButton
            {...authProps}
            action="login"
            source="header"
            className="lp-signin-top"
            shortLabel="Sign in"
          />
          <AuthButton
            {...authProps}
            action="signup"
            source="header"
            className="lp-signup-top"
            shortLabel="Sign up"
          />
        </div>
      </header>

      <main className="lp-frame" id="landing-main">
        <section className="lp-hero">
          <div className="lp-wrap">
            {/* Temporary demo: join a live game with a code and nickname,
                no account needed (src/guest). */}
            <div className="lp-guest-join">
              <Link className="lp-guest-join-button" to="/play">
                Join a game <span aria-hidden="true">→</span>
              </Link>
              <p>No account needed: just the game code and a nickname.</p>
            </div>

            <div className="lp-hero-top">
              <div className="lp-hero-copy">
                <p className="lp-eyebrow">
                  Gettysburg College · Live class quizzes
                </p>

                <h1>
                  Ask the room.
                  <br />
                  <span className="lp-highlight">Everyone answers.</span>
                </h1>
              </div>

              <div className="lp-hero-side">
                <p className="lp-lede">
                  The question goes up on the big screen. Everyone answers on
                  their phone. Results land the second it&apos;s over.
                </p>

                <div
                  className="lp-auth-actions"
                  aria-busy={pending?.source === "hero"}
                >
                  <AuthButton
                    {...authProps}
                    action="login"
                    source="hero"
                    className="lp-button"
                    arrow
                  />
                  <AuthButton
                    {...authProps}
                    action="signup"
                    source="hero"
                    className="lp-button lp-button-secondary"
                  />
                </div>

                <p className="lp-fine">
                  Email and password. New passwords need 8+ characters,
                  including a symbol.
                </p>
              </div>
            </div>

            {heroError && (
              <p className="lp-error" role="alert" ref={heroErrorRef}>
                {heroError}
              </p>
            )}
          </div>

          <div className="lp-devices" aria-hidden="true">
            <div className="lp-screen">
              <div className="lp-screen-top">
                <span>Live session · Question 3 of 8</span>
                <span className="lp-time">0:12</span>
              </div>

              <div className="lp-screen-body">
                <h3>What is the worst-case time of binary search?</h3>

                <div className="lp-screen-grid">
                  <div>A · O(n)</div>
                  <div>B · O(log n)</div>
                  <div>C · O(1)</div>
                  <div>D · O(n log n)</div>
                </div>

                <p className="lp-screen-foot">
                  <b>19</b> of 24 answered
                </p>
              </div>
            </div>

            <div className="lp-phone">
              <div className="lp-notch" />
              <p>Worst-case time of binary search?</p>
              <div>A · O(n)</div>
              <div className="lp-picked">B · O(log n)</div>
              <div>C · O(1)</div>
            </div>
          </div>
        </section>

        <section className="lp-chapters" id="how" aria-label="How it works">
          <aside className="lp-rail">
            <div className="lp-rail-inner">
              <span className="lp-big-number">
                {String(activeChapter + 1).padStart(2, "0")}
              </span>

              <span className="lp-rail-title">
                {chapters[activeChapter].title}
              </span>

              <nav aria-label="Chapters">
                <ol>
                  {chapters.map((chapter, index) => (
                    <li key={chapter.id}>
                      <a
                        href={`#${chapter.id}`}
                        className={
                          index === activeChapter
                            ? "lp-current"
                            : index < activeChapter
                              ? "lp-complete"
                              : ""
                        }
                        aria-current={
                          index === activeChapter ? "step" : undefined
                        }
                        aria-label={chapter.title}
                      >
                        <i aria-hidden="true" />
                        <span>{chapter.title}</span>
                      </a>
                    </li>
                  ))}
                </ol>
              </nav>
            </div>
          </aside>

          <div>
            {chapters.map((chapter, index) => (
              <article
                className="lp-chapter"
                id={chapter.id}
                key={chapter.id}
                ref={(element) => {
                  chapterRefs.current[index] = element;
                }}
              >
                <div>
                  <p className="lp-eyebrow">
                    Chapter {String(index + 1).padStart(2, "0")}
                  </p>
                  <h2>{chapter.heading}</h2>
                  <p>{chapter.description}</p>
                </div>

                <ChapterPreview chapter={chapter.id} />
              </article>
            ))}
          </div>
        </section>

        <section id="who">
          <div className="lp-wrap">
            <p className="lp-eyebrow">Who it&apos;s for</p>
            <h2>One account. Join or host.</h2>

            <p>
              Every User can participate in quizzes and host quizzes they
              create. Host and participant describe what you do in a session,
              not separate account roles.
            </p>

            <div className="lp-who">
              <div className="lp-who-card">
                <h3>Participate</h3>
                <ul>
                  <li>Sign in and join a live session with its code.</li>
                  <li>Answer questions from your phone or computer.</li>
                  <li>Review your own answers, score, and rank afterward.</li>
                </ul>
              </div>

              <div className="lp-who-card">
                <h3>Host</h3>
                <ul>
                  <li>Create and save a complete public quiz.</li>
                  <li>Host a quiz you created and share its session code.</li>
                  <li>View and export results for sessions you hosted.</li>
                </ul>
              </div>
            </div>

            <p className="lp-fine">
              The account roles are User and Admin. Admins can access all
              session results and export them.
            </p>
          </div>
        </section>

        <section className="lp-cta">
          <div className="lp-wrap">
            <h2>Start with one question. See what the room thinks.</h2>

            <div className="lp-cta-box">
              <div
                className="lp-auth-actions"
                aria-busy={pending?.source === "cta"}
              >
                <AuthButton
                  {...authProps}
                  action="login"
                  source="cta"
                  className="lp-button"
                  arrow
                />
                <AuthButton
                  {...authProps}
                  action="signup"
                  source="cta"
                  className="lp-button lp-button-secondary"
                />
              </div>

              <p className="lp-fine">
                One account for participating and presenting.
              </p>

              {ctaError && (
                <p className="lp-error" role="alert" ref={ctaErrorRef}>
                  {ctaError}
                </p>
              )}
            </div>
          </div>
        </section>
      </main>

      <footer className="lp-footer">
        <span>QuizBurg · Gettysburg College</span>
        <span>Built by the CS 440 team · Fall 2026</span>
      </footer>
    </div>
  );
}
