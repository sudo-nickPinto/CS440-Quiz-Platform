import { useEffect, useRef, useState } from 'react'
import LoginPage from './components/LoginPage'
import LobbyPage from './components/LobbyPage'
import './App.css'

export default function App() {
  // Mock identity only: no credentials or sessions are persisted.
  const [user, setUser] = useState(null)
  const heading = useRef(null)
  useEffect(() => { heading.current?.focus() }, [user])
  return <>
    <a className="skip-link" href="#main">Skip to content</a>
    <header className="site-header">
      <a className="brand" href="#main" aria-label="Classroom Quiz home">
        <span className="brand-mark" aria-hidden="true">Q</span>
        <span>Classroom<span className="brand-light">Quiz</span></span>
      </a>
      <div className="header-actions">
        <span className="demo-badge">Frontend demo</span>
        {user && <button className="text-button" onClick={() => setUser(null)}>Log out</button>}
      </div>
    </header>
    <main id="main">
      {user ? <LobbyPage user={user} headingRef={heading} /> : <LoginPage onLogin={setUser} headingRef={heading} />}
    </main>
    <footer>CS 440 · Gettysburg College <span>Made for a more connected classroom.</span></footer>
  </>
}
