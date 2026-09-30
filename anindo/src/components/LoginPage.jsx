import { useState } from 'react'
import { DEMO_ACCOUNT } from '../demo'

export default function LoginPage({ onLogin, headingRef }) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [error, setError] = useState('')
  function handleSubmit(event) {
    event.preventDefault()
    if (username.trim() !== DEMO_ACCOUNT.username || password !== DEMO_ACCOUNT.password) {
      setError('Unable to log in. Check your username and password and try again.')
      return
    }
    onLogin({ name: 'Demo User', username: DEMO_ACCOUNT.username })
  }
  return <div className="login-layout">
    <section className="intro-panel" aria-labelledby="intro-title">
      <p className="eyebrow">GETTYSBURG COLLEGE · CS 440</p>
      <h2 id="intro-title">Classroom <span>Quiz</span></h2>
      <p className="intro-copy">A shared space for classroom questions, participation, and learning.</p>
      <p className="intro-detail">Join a live session or bring your class together with a quiz of your own.</p>
    </section>
    <section className="login-form-panel" aria-labelledby="login-title">
      <h1 id="login-title" ref={headingRef} tabIndex={-1}>Welcome back</h1>
      <p className="muted">Log in to join a quiz or host your own.</p>
      <form onSubmit={handleSubmit}>
        <label htmlFor="username">Username</label>
        <input id="username" name="username" autoComplete="username" required maxLength={80}
          value={username} onChange={(e) => { setUsername(e.target.value); setError('') }}
          aria-describedby={error ? 'login-error' : undefined} placeholder="Enter your username" />
        <label htmlFor="password">Password</label>
        <div className="password-field">
          <input id="password" name="password" type={showPassword ? 'text' : 'password'}
            autoComplete="current-password" required value={password}
            onChange={(e) => { setPassword(e.target.value); setError('') }}
            aria-describedby={error ? 'login-error' : undefined} placeholder="Enter your password" />
          <button type="button" className="text-button" aria-controls="password" aria-pressed={showPassword}
            onClick={() => setShowPassword(!showPassword)}>{showPassword ? 'Hide' : 'Show'}</button>
        </div>
        {error && <p id="login-error" className="error" role="alert">{error}</p>}
        <button className="primary full-width" type="submit">Log in <span aria-hidden="true">→</span></button>
      </form>
      <aside className="demo-note">
        <strong>Demo account</strong>
        <p>Username: <code>demo</code> · Password: <code>quiz440</code></p>
        <p>Use these fictional credentials only. This demo does not create accounts or authenticate with a server.</p>
      </aside>
    </section>
  </div>
}
