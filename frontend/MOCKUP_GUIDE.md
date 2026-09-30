# Login and lobby mockup

This React mockup implements the login and lobby views from the working SRS. It runs inside the repository's existing Vite frontend. No new dependencies, backend, database, or environment variables are needed.

The design uses a Kahoot-inspired purple stage, bold type, red/blue/yellow/green shapes, a centered login and code-entry form, and a large host code banner with player tiles. The SRS takes precedence over Kahoot's flow: participants log in with local accounts before entering a session code. The roster appears only after joining. QR joining and SSO remain outside this mockup.

## 1. Open the prepared project

The completed code is already in this local clone, on `feature/login-lobby-mockup`:

```powershell
cd "D:\Gettysburg College\Study Material\Fall 2026\CS440\CS440-Quiz-Platform"
git branch --show-current
```

Open this folder in your editor. If using VS Code with its command installed, run `code .`.

If starting on another computer, clone the repository, create your feature branch, and copy the seven code files listed below plus this guide into the same relative locations. Do not overwrite other people's newer frontend work without reviewing the differences.

```powershell
git clone https://github.com/sudo-nickPinto/CS440-Quiz-Platform.git
cd CS440-Quiz-Platform
git switch -c feature/login-lobby-mockup
```

## 2. Understand the code

| File | Responsibility |
| --- | --- |
| `src/App.jsx` | Header, footer, in-memory login state, and switching between screens |
| `src/components/LoginPage.jsx` | Controlled username/password inputs, show/hide password, validation, and login form |
| `src/components/LobbyPage.jsx` | Code entry, waiting room, participant list, leaving, copying a code, and host preview |
| `src/demo.js` | Fictional credentials, session code, quiz metadata, and classmates |
| `src/index.css` | Global typography, focus indicators, and base styles |
| `src/App.css` | Page layouts, cards, colors, and responsive breakpoints |
| `index.html` | Browser title and page metadata |

`src/main.jsx` already imports the global stylesheet and renders App, so it requires no changes.

To build this yourself: first define the fixtures in `demo.js`; then build the login form and call `onLogin` on successful validation; use App state to render the lobby; implement session-code validation and a `joined` state; add the host preview and reset controls; finally apply global and component styles. Read the complete files above for the working implementation.

In React, `useState` stores form values and the current screen state. Input `onChange` handlers update that state. Form handlers call `preventDefault()` to avoid reloading the page. Conditional JSX selects the correct UI. `participants.map()` renders the roster; CSS Grid arranges panels and media queries stack them on phones. Heading refs move keyboard focus when a screen changes.

## 3. Install and run

Install Node.js and Git if needed. Use a Node version supported by the versions in the existing lockfile. Then:

```powershell
cd frontend
npm.cmd ci
npm.cmd run dev
```

Open the localhost URL printed by Vite, usually `http://localhost:5173`. Leave the terminal running; stop it with Ctrl+C. `npm.cmd` avoids PowerShell script-policy issues with `npm.ps1`. On macOS/Linux, use `npm` instead.

## 4. Try each interaction

1. Enter username `demo` and an incorrect password. Expect a general login error.
2. Enter password `quiz440`. Try Show/Hide, then press Log in (or Enter).
3. Enter `123456` as the session code. Expect a session-not-found error.
4. Enter `440126` and press Enter. Expect the waiting room, seven participants including Demo User, and the waiting message.
5. Try Copy code. If clipboard access is unavailable, the message explains how to copy manually.
6. Click Leave lobby. The join form returns.
7. Click Host preview. The demo host lobby shows six fictional participants.
8. Click Start quiz preview. A message confirms the simulated start; Reset lobby preview restores the waiting state.
9. Click Log out. The login screen returns. Refreshing also resets all demo state.
10. Check at phone width and at 200% browser zoom. Tab through forms and buttons; use Enter to submit. All controls should remain reachable without horizontal scrolling.

Host preview and Join a quiz are views available to the same User account. They do not assign Teacher or Administrator permissions.

## 5. Check the code before committing

From `frontend`:

```powershell
npm.cmd run lint
npm.cmd run build
```

The production output is generated in `dist`, which Git ignores. Do not commit `node_modules` or `dist`. Google Fonts is optional: the CSS falls back to local sans-serif fonts when offline.

## 6. Commit and push your feature branch

From `frontend`, return to the repository root and inspect the changes:

```powershell
cd ..
git status
git diff --check
git diff
git add frontend/src/App.jsx frontend/src/App.css frontend/src/index.css frontend/src/components/LoginPage.jsx frontend/src/components/LobbyPage.jsx frontend/src/demo.js frontend/index.html frontend/MOCKUP_GUIDE.md
git diff --cached --stat
git commit -m "Add login and lobby frontend mockup"
git push -u origin feature/login-lobby-mockup
```

If Git asks for your identity, configure your own name and GitHub email in this repository using `git config user.name "Your Name"` and `git config user.email "your-email"`, then retry the commit. Complete GitHub's authentication prompt if needed. A permission-denied error means your account needs collaborator access or you must push to a fork; do not force-push.

## 7. Open a pull request

Open https://github.com/sudo-nickPinto/CS440-Quiz-Platform and choose **Compare & pull request**. Select base `main` and compare `feature/login-lobby-mockup`.

Suggested title: **Add login and lobby frontend mockup**

Suggested description (update verification to match checks you completed):

> Replaces the Vite starter screen with a responsive local-login mockup, session-code entry, participant waiting room, and host lobby preview. Includes demo validation, password visibility, copy/leave/logout controls, and setup instructions. All credentials and roster entries are fictional; backend authentication and live synchronization are not implemented. Validation: frontend build and lint, plus manual login and lobby checks.

Create the pull request and ask your team to review it. Pushing a branch uploads code; it does not deploy the app or merge it into main.

## SRS alignment and integration boundaries

- Sections 4.1 and 5.1: username/password local login and a general invalid-credentials message. Registration is outside these two requested mockup pages.
- FR-5.1.8: one User can participate and host; no role selector grants privileges.
- FR-5.4.2–5.4.5: code display/entry, waiting lobby, and host start control are represented visually. Session creation and start are fixtures/simulations.
- NF-6.3: responsive layout, labels, keyboard controls, focus management, and status/error announcements support accessibility. A complete assistive-technology/browser audit is still needed.
- The six-digit code, fictional names, colors, quiz title, and invalid-code behavior are prototype choices. The SRS leaves exceptional session behavior and code format open.

Before production, replace credential comparisons with the team's FastAPI authentication flow, keep password hashing on the server, obtain server-authorized identity and permissions, and replace demo fixtures with session data. Agree on actual API routes and WebSocket/polling messages with the backend team; the SRS does not finalize them. Validate joining, session status, and host actions on the server. Route server start events to the quiz screen. This mockup stores nothing and synchronizes neither tabs nor devices; its client state is not access control.
