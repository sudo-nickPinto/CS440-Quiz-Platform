import { useEffect, useRef, useState } from 'react'
import { useAuth0 } from '@auth0/auth0-react'
import './LandingPage.css'

const chapters = [
  {
    id: 'build',
    title: 'Build',
    heading: 'Create it. Check it. Save it.',
    description:
      'Add your questions, answer choices, correct answers, and time limits. Check the complete quiz before saving: saving makes it public and published immediately, and saved quizzes cannot be edited.',
  },
  {
    id: 'shared',
    title: 'Share',
    heading: 'One shared class. Everyone included.',
    description:
      'Everyone with an account belongs to the same shared class. Saved quizzes are public, with no class selection or enrollment step. Create your own quiz to host a session, then share its join code.',
  },
  {
    id: 'present',
    title: 'Present',
    heading: 'Open the lobby. Hit go.',
    description:
      'Host a quiz you created and share the session code. Any signed-in user can join as a participant. Watch the lobby fill up, then start the questions and guide the session.',
  },
  {
    id: 'review',
    title: 'Review',
    heading: 'See how the session went.',
    description:
      'Participants see their own answers, score, and rank. Hosts can view and export results for sessions they hosted, and Admins can access all results. Each session keeps its own results, and saved quizzes stay unchanged.',
  },
]

const sampleParticipants = [
  'AM', 'NP', 'UK', 'PD', 'TS',
  'JL', 'RB', 'KW', 'EO', 'MG',
]

function ChapterPreview({ chapter }) {
  if (chapter === 'build') {
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
            {['10s', '20s', '30s', '60s'].map((time) => (
              <span
                key={time}
                className={time === '20s' ? 'lp-selected' : ''}
              >
                {time}
              </span>
            ))}
          </div>
        </div>
      </div>
    )
  }

  if (chapter === 'shared') {
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
            Saving publishes the complete quiz immediately.
            Saved quizzes cannot be edited.
          </p>
        </div>
      </div>
    )
  }

  if (chapter === 'present') {
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
              <span
                key={index}
                className={index < 10 ? 'lp-present' : ''}
              >
                {sampleParticipants[index] || '·'}
              </span>
            ))}
          </div>

          <div className="lp-go">
            <span>10 participants joined</span>
            <span className="lp-start-example">Start →</span>
          </div>
        </div>
      </div>
    )
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
            className={`lp-result ${index > 0 ? 'lp-result-dim' : ''}`}
          >
            <span className="lp-rank">{index + 1}</span>

            <span className="lp-result-name">
              {index === 0 ? 'You' : 'Classmate'}
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
  )
}

export default function LandingPage({ authError = '' }) {
  const { loginWithRedirect } = useAuth0()

  const [signInOpen, setSignInOpen] = useState(false)
  const [pending, setPending] = useState('')
  const [loginError, setLoginError] = useState('')
  const [activeChapter, setActiveChapter] = useState(0)

  const heroRef = useRef(null)
  const loginTitleRef = useRef(null)
  const triggerRef = useRef(null)
  const chapterRefs = useRef([])

  const busy = pending !== ''
  const visibleError = loginError || authError

  // Move keyboard focus into the inline card when it opens.
  useEffect(() => {
    if (!signInOpen) return

    loginTitleRef.current?.focus({ preventScroll: true })

    function handleEscape(event) {
      if (event.key === 'Escape' && !busy) {
        setSignInOpen(false)
        triggerRef.current?.focus({ preventScroll: true })
      }
    }

    document.addEventListener('keydown', handleEscape)

    return () => {
      document.removeEventListener('keydown', handleEscape)
    }
  }, [signInOpen, busy])

  // Track the chapter closest to the middle of the viewport.
  useEffect(() => {
    let frameId = 0

    function updateActiveChapter() {
      const midpoint = window.innerHeight * 0.5
      let nextChapter = 0

      chapterRefs.current.forEach((element, index) => {
        if (element && element.getBoundingClientRect().top < midpoint) {
          nextChapter = index
        }
      })

      setActiveChapter(nextChapter)
    }

    function scheduleUpdate() {
      window.cancelAnimationFrame(frameId)
      frameId = window.requestAnimationFrame(updateActiveChapter)
    }

    scheduleUpdate()
    window.addEventListener('scroll', scheduleUpdate, { passive: true })
    window.addEventListener('resize', scheduleUpdate)

    return () => {
      window.cancelAnimationFrame(frameId)
      window.removeEventListener('scroll', scheduleUpdate)
      window.removeEventListener('resize', scheduleUpdate)
    }
  }, [])

  function openSignIn(event) {
    triggerRef.current = event.currentTarget
    setLoginError('')
    setSignInOpen(true)

    const reduceMotion = window.matchMedia(
      '(prefers-reduced-motion: reduce)',
    ).matches

    heroRef.current?.scrollIntoView({
      behavior: reduceMotion ? 'auto' : 'smooth',
      block: 'start',
    })
  }

  function closeSignIn() {
    if (busy) return

    setSignInOpen(false)
    setLoginError('')
    triggerRef.current?.focus({ preventScroll: true })
  }

  async function startLogin(action) {
    if (busy) return

    setLoginError('')
    setPending(action)

    const authorizationParams = {}

    if (action === 'google') {
      authorizationParams.connection = 'google-oauth2'
    }

    if (action === 'signup') {
      authorizationParams.screen_hint = 'signup'
    }

    try {
      await loginWithRedirect({
        authorizationParams,
        // Keep the existing application's back-button behavior.
        openUrl: (url) => window.location.replace(url),
      })
    } catch {
      setLoginError('We could not open sign-in. Please try again.')
    } finally {
      setPending('')
    }
  }

  return (
    <div className="lp">
      <a className="lp-skip" href="#landing-main">
        Skip to content
      </a>

      <header className="lp-header">
        <a className="lp-logo" href="#landing-main">
          QUIZ<span>.</span>PLATFORM
        </a>

        <nav className="lp-nav" aria-label="Page sections">
          <a href="#how">How it works</a>
          <a href="#who">Who it&apos;s for</a>
        </nav>

        <button
          className="lp-signin-top"
          type="button"
          onClick={openSignIn}
          aria-controls="landing-signin"
          aria-expanded={signInOpen}
        >
          Sign in
        </button>
      </header>

      <main className="lp-frame" id="landing-main">
        <section className="lp-hero" ref={heroRef}>
          <div className="lp-wrap">
            <div className={`lp-hero-top ${signInOpen ? 'lp-open' : ''}`}>
              <div className="lp-hero-copy">
                <p className="lp-eyebrow">
                  {signInOpen
                    ? 'Sign in · Your classroom starts here'
                    : 'Gettysburg College · Live class quizzes'}
                </p>

                <h1>
                  Ask the room.
                  <br />
                  <span className="lp-highlight">Everyone answers.</span>
                </h1>
              </div>

              {!signInOpen && (
                <div className="lp-hero-side">
                  <p className="lp-lede">
                    The question goes up on the big screen. Everyone
                    answers on their phone. Results land the second
                    it&apos;s over.
                  </p>

                  <button
                    className="lp-button"
                    type="button"
                    onClick={openSignIn}
                    aria-controls="landing-signin"
                    aria-expanded={false}
                  >
                    Sign in <span aria-hidden="true">→</span>
                  </button>

                  <p className="lp-fine">
                    Use your existing account or continue with Google.
                  </p>
                </div>
              )}

              <section
                className="lp-login-card"
                id="landing-signin"
                aria-labelledby="landing-signin-title"
                hidden={!signInOpen}
              >
                <div className="lp-login-top">
                  <span>Sign in</span>
                  <span>Secure access</span>

                  <button
                    type="button"
                    aria-label="Close sign-in"
                    onClick={closeSignIn}
                    disabled={busy}
                  >
                    ×
                  </button>
                </div>

                <div className="lp-login-body">
                  <h2
                    id="landing-signin-title"
                    ref={loginTitleRef}
                    tabIndex={-1}
                  >
                    Pull up a <span>seat.</span>
                  </h2>

                  <p>
                    Sign in to access your quizzes and classroom
                    activities.
                  </p>

                  <div className="lp-login-actions" aria-busy={busy}>
                    <button
                      className="lp-button"
                      type="button"
                      disabled={busy}
                      onClick={() => startLogin('login')}
                    >
                      {pending === 'login' ? 'Opening sign-in…' : 'Sign in'}
                      <span aria-hidden="true">→</span>
                    </button>

                    <button
                      className="lp-button lp-button-secondary"
                      type="button"
                      disabled={busy}
                      onClick={() => startLogin('google')}
                    >
                      {pending === 'google'
                        ? 'Opening Google…'
                        : 'Continue with Google'}
                    </button>

                    <p className="lp-fine">
                      New here?{' '}
                      <button
                        className="lp-text-button"
                        type="button"
                        disabled={busy}
                        onClick={() => startLogin('signup')}
                      >
                        {pending === 'signup'
                          ? 'Opening registration…'
                          : 'Create an account'}
                      </button>
                    </p>
                  </div>

                  <p className="lp-login-status" role="status">
                    {busy ? 'Opening the secure sign-in page…' : ''}
                  </p>
                </div>
              </section>
            </div>

            {visibleError && (
              <p className="lp-error" role="alert">
                {visibleError}
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
                {String(activeChapter + 1).padStart(2, '0')}
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
                            ? 'lp-current'
                            : index < activeChapter
                              ? 'lp-complete'
                              : ''
                        }
                        aria-current={
                          index === activeChapter ? 'step' : undefined
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
                  chapterRefs.current[index] = element
                }}
              >
                <div>
                  <p className="lp-eyebrow">
                    Chapter {String(index + 1).padStart(2, '0')}
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
              create. Host and participant describe what you do in a
              session, not separate account roles.
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
              <button
                className="lp-button"
                type="button"
                onClick={openSignIn}
                aria-controls="landing-signin"
                aria-expanded={signInOpen}
              >
                Sign in <span aria-hidden="true">→</span>
              </button>

              <p className="lp-fine">
                One account for participating and presenting.
              </p>
            </div>
          </div>
        </section>
      </main>

      <footer className="lp-footer">
        <span>QUIZ.PLATFORM · Gettysburg College</span>
        <span>Built by the CS 440 team · Fall 2026</span>
      </footer>
    </div>
  )
}