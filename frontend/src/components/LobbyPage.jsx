import { useEffect, useRef, useState } from 'react'
import { DEMO_SESSION } from '../demo'

export default function LobbyPage({ user, headingRef }) {
  const [mode, setMode] = useState('participant')
  const [code, setCode] = useState('')
  const [joined, setJoined] = useState(false)
  const [started, setStarted] = useState(false)
  const [error, setError] = useState('')
  const [copyMessage, setCopyMessage] = useState('')
  const stateHeading = useRef(null)
  const isHost = mode === 'host'
  const inLobby = isHost || joined
  const participants = joined ? [...DEMO_SESSION.participants, user.name] : DEMO_SESSION.participants
  useEffect(() => { stateHeading.current?.focus() }, [joined, mode, started])

  function changeMode(nextMode) {
    setMode(nextMode)
    setJoined(false)
    setStarted(false)
    setCode('')
    setError('')
    setCopyMessage('')
  }
  function joinSession(event) {
    event.preventDefault()
    if (code.trim() !== DEMO_SESSION.code) {
      setError('Session not found. For this demo, enter 440126.')
      return
    }
    setError('')
    setJoined(true)
  }
  async function copyCode() {
    try {
      await navigator.clipboard.writeText(DEMO_SESSION.code)
      setCopyMessage('Session code copied.')
    } catch {
      setCopyMessage('Copy unavailable. Select the code and copy it manually.')
    }
  }
  return <div className={`lobby-layout ${inLobby ? 'active-lobby' : 'join-screen'} ${isHost ? 'host-view' : ''}`}>
    <div className="page-heading">
      <div><p className="eyebrow">{isHost ? 'HOST SCREEN' : `SIGNED IN AS ${user.name}`}</p>
        <h1 ref={headingRef} tabIndex={-1}>{isHost ? 'Let’s get everyone in!' : joined ? 'You’re on the team!' : 'Let’s play!'}</h1>
        <p className="muted">{isHost ? 'Display this lobby on the classroom screen.' : joined ? 'Look up at the host’s screen. Your quiz will begin soon.' : 'Enter your session code to join the fun.'}</p>
      </div>
      <div className="mode-switch" role="group" aria-label="Choose a demo view">
        <button aria-pressed={!isHost} onClick={() => changeMode('participant')}>Join a quiz</button>
        <button aria-pressed={isHost} onClick={() => changeMode('host')}>Host preview</button>
      </div>
    </div>
    <div className="lobby-grid">
      <section className="card session-card" aria-labelledby="session-title">
        <p className="eyebrow">{isHost ? 'JOIN CLASSROOM QUIZ WITH THIS CODE' : joined ? 'YOU’VE JOINED THE SESSION' : 'JOIN A LIVE QUIZ'}</p>
        <h2 id="session-title" ref={stateHeading} tabIndex={-1}>
          {started ? 'Get ready!' : isHost ? 'Session code' : joined ? 'You’re in!' : 'Session code'}
        </h2>
        {!inLobby ? <>
          <p className="muted">Use the code on your host’s screen.</p>
          <form onSubmit={joinSession}>
            <label htmlFor="session-code">Session code</label>
            <input id="session-code" className="code-input" inputMode="numeric" autoComplete="off"
              required maxLength={6} value={code} placeholder="000000"
              aria-describedby={error ? 'code-error code-help' : 'code-help'} aria-invalid={Boolean(error)}
              onChange={(e) => { setCode(e.target.value); setError('') }} />
            <p id="code-help" className="field-help">Try the demo code: <strong>440126</strong></p>
            {error && <p id="code-error" className="error" role="alert">{error}</p>}
            <button className="primary full-width">Enter <span aria-hidden="true">→</span></button>
          </form>
        </> : <>
          <p className="muted">{isHost ? 'Log in on your device, then enter the session code.' : `Playing as ${user.name}`}</p>
          <div className="session-code-box">
            <span>SESSION CODE</span><strong className="session-code">{DEMO_SESSION.code}</strong>
            <button className="text-button" onClick={copyCode}>Copy code</button>
            <p className="field-help" role="status">{copyMessage}</p>
          </div>
          <div className="waiting-state" role="status"><span className="status-dot" aria-hidden="true" />
            {started ? 'Start simulated — quiz screen is outside this mockup.' : isHost ? 'Your classroom is ready when you are.' : 'Waiting for the host to start…'}
          </div>
          {isHost
            ? <button className="primary full-width" onClick={() => setStarted(!started)}>{started ? 'Reset lobby preview' : 'Start quiz preview →'}</button>
            : <button className="secondary full-width" onClick={() => { setJoined(false); setCopyMessage('') }}>Leave lobby</button>}
        </>}
      </section>
      {inLobby && <section className="card room-card" aria-labelledby="room-title">
        <div className="room-header"><span className="pill">{started ? 'START PREVIEW' : 'WAITING ROOM'}</span><span className="muted">CS 440</span></div>
        <h2 id="room-title">{DEMO_SESSION.title}</h2>
        <p className="muted">Hosted by {isHost ? user.name : DEMO_SESSION.host} · {DEMO_SESSION.questionCount} questions</p>
        <div className="participant-heading"><span className="count">{participants.length}</span><h3>Players in the lobby</h3></div>
        <ul className="participant-list">
          {participants.map((name, index) => <li key={name}>
            <span className={`avatar tone-${index % 4}`} aria-hidden="true">{name.split(' ').map((part) => part[0]).join('')}</span>
            <span>{name}{name === user.name && <small> (you)</small>}</span>
          </li>)}
        </ul>
        <p className="room-tip">{isHost ? 'Everyone here? Start the quiz when your classroom is ready.' : 'You’re all set. Stay on this page until your host starts the quiz.'}</p>
      </section>}
    </div>
    <div className="answer-tiles lobby-shapes" aria-hidden="true"><span>▲</span><span>◆</span><span>●</span><span>■</span></div>
    <p className="mockup-disclosure">Mockup only · Classmates are fictional. Views run independently; no live session or backend is connected. Refreshing resets the demo.</p>
  </div>
}
