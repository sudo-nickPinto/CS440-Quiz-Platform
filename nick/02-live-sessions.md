# Live sessions: the protocol and the WebSocket proof of concept

**PRs:** [#36](https://github.com/sudo-nickPinto/CS440-Quiz-Platform/pull/36) (protocol doc) · [#38](https://github.com/sudo-nickPinto/CS440-Quiz-Platform/pull/38) (WebSocket PoC)
**Course week:** 8 (Oct 12, 2026)
**Roadmap owner:** Nick was the proposed owner of the protocol doc, the WebSocket PoC, the live controls and reconnect handling (`docs/ROADMAP.md`).

## In plain terms

Most of the app works like a normal website: the browser asks, the server answers. A live quiz game doesn't fit that. When the host starts question 3, every player's phone has to switch to question 3 **at the same moment**, without anyone refreshing.

A **WebSocket** is a phone line that stays open between each browser and the server, so the server can push news ("question 3 is open", "time's up", "here's the leaderboard") the instant it happens.

By Week 8, teammates had already built the game's *rules* as backend services: creating and joining a session (Anh, #28), scoring answers (Pronob, #27), opening and closing questions (Pronob, #35), and the leaderboard (Pronob, #34). Nothing connected those rules to players in real time yet. Nick's two PRs are that connection:

1. **#36, the rulebook.** It defines exactly which messages the host screen, player screens and server send each other, and what each one means. Front-end and back-end developers can build against it independently.
2. **#38, the working prototype.** A real server endpoint where a host and players can actually play questions live, tested end to end with one host and two players.

**The one rule behind everything:** the database is the source of truth, and the WebSocket only carries news about it. The server always saves to MySQL first, then tells everyone. A player who reconnects gets a fresh snapshot from the database rather than a replay of what they missed.

## How the pieces fit

```mermaid
flowchart TB
    subgraph Clients
        H["Host screen"]
        P1["Player phone"]
        P2["Player phone"]
    end

    subgraph Nick["WebSocket layer (Nick, #38): backend/app/live/"]
        EP["routes/live.py<br/>/ws/sessions/{id}"]
        AUTH["live/auth.py<br/>first-message login"]
        HUB["live/hub.py<br/>who is connected, broadcast,<br/>deadline timers"]
        SNAP["live/snapshot.py<br/>session_state + per-role<br/>results view"]
        PROTO["live/protocol.py<br/>message shapes (Pydantic)"]
    end

    subgraph Services["Game rules (teammates)"]
        SESS["sessions.py<br/>create / join (Anh #28)"]
        LQ["live_questions.py<br/>open / close (Pronob #35)"]
        RS["responses.py + scoring.py<br/>answers (Pronob #27)"]
        RES["results.py<br/>leaderboard (Pronob #34)"]
    end

    DB[("MySQL")]

    H <--> EP
    P1 <--> EP
    P2 <--> EP
    EP --> AUTH
    EP --> PROTO
    EP --> HUB
    HUB --> SNAP
    EP --> LQ
    EP --> RS
    HUB --> LQ
    SNAP --> RES
    SNAP --> SESS
    SESS --> DB
    LQ --> DB
    RS --> DB
    RES --> DB
```

## The states a game goes through

**A session** (one play-through of a quiz):

```mermaid
stateDiagram-v2
    [*] --> LOBBY: host creates session (6-digit code)
    LOBBY --> ACTIVE: host opens question 1
    LOBBY --> CANCELLED: host cancels
    ACTIVE --> COMPLETED: host ends the game
    COMPLETED --> [*]
    CANCELLED --> [*]
```

**A question** inside a session:

```mermaid
stateDiagram-v2
    [*] --> OPEN: host opens the next question
    OPEN --> CLOSED: everyone answered (ALL_ANSWERED)
    OPEN --> CLOSED: timer ran out (DEADLINE)
    OPEN --> CLOSED: host skips (HOST)
    CLOSED --> [*]
```

Questions open strictly in order, one at a time, and a closed question never reopens. The server sets the timer; the phone's clock is only used to draw the countdown.

## User flow: playing a live game

```mermaid
flowchart TD
    subgraph Host
        H1["Create session from a quiz"] --> H2["Lobby: show join code,<br/>watch player count"]
        H2 --> H3["Open next question"]
        H3 --> H4["Watch answers come in<br/>(3 of 5 answered)"]
        H4 --> H5["See full results +<br/>full leaderboard"]
        H5 -->|"more questions"| H3
        H5 -->|"last question"| H6["End game"]
    end

    subgraph Player
        P1["Enter join code"] --> P2["Waiting room"]
        P2 --> P3["See colored answer buttons,<br/>tap one"]
        P3 --> P4["'Answer submitted'<br/>(no score yet)"]
        P4 --> P5["See correct answer,<br/>own points, rank, top 5"]
        P5 -->|"next question"| P3
        P5 -->|"game over"| P6["Final screen"]
    end

    H3 -.->|"question_opened"| P3
    P3 -.->|"submit_answer"| H4
    H4 -.->|"question_closed +<br/>question_results"| P5
```

Players never see whether they were right until the question closes (a rule from Pronob's #27). After it closes, a player sees only their own row plus the top 5. The host sees everyone.

## Connecting securely

Browsers can't attach a login header to a WebSocket, and putting the token in the URL would leak it into server logs. So the protocol makes the **first message** the login:

```mermaid
sequenceDiagram
    autonumber
    participant C as Browser
    participant S as Server
    participant DB as MySQL

    C->>S: open /ws/sessions/12
    C->>S: {"type":"auth","token":"..."} (within 5 s)
    S->>S: verify token exactly like HTTP (Auth0 keys)
    S->>DB: get_or_create_account, is_active?
    S->>DB: host_id = me? or un-left participant row?
    alt allowed
        S-->>C: session_state snapshot
    else not allowed
        S--xC: close with a code (see table)
    end
```

| Close code | Meaning | What the screen should do |
|---|---|---|
| `1000` | Session ended normally | Show the final screen |
| `4400` | Malformed message, or the first message wasn't `auth` | Bug: log it |
| `4401` | Missing, invalid or expired token, or took longer than 5 s | Get a new token, reconnect once, then go to login |
| `4403` | Not the host or a participant, or account inactive | Go to the dashboard |
| `4404` | Session not found | Go to the dashboard |
| `4409` | Same account opened the game in another tab | Show "opened in another tab" |
| `4410` | Session already completed or cancelled | Show the final screen |
| `1011` | Server error | Reconnect with backoff (1 s, 2 s, 4 s … max 30 s) |

## Closing a question exactly once

This was the trickiest part. Three things can end a question: the **last player answering**, the **timer running out**, and the **host skipping**. These can happen at almost the same instant. If two of them both announced "time's up", every phone would get the results twice.

The fix: all three paths call Pronob's `close_question_if_ready()`, which flips the question from `OPEN` to `CLOSED` with a single database update that only one caller can win. **Only the winner broadcasts.**

```mermaid
sequenceDiagram
    autonumber
    participant H as Host
    participant S as WebSocket server
    participant DB as MySQL
    participant P as Players

    H->>S: open_question {question_order: 1}
    S->>DB: open_question() saves OPEN, opened_at, closes_at
    S-->>P: question_opened (everyone)
    S->>S: start timer for closes_at + 250 ms
    P->>S: submit_answer
    S->>DB: submit_response() saves the scored answer
    S-->>P: ack (sender only, no points)
    S-->>H: answer_progress (answered / eligible)
    S->>DB: close_question_if_ready()
    alt this caller won the update
        DB-->>S: QuestionClosedEvent
        S-->>P: question_closed (everyone)
        S->>DB: get_closed_question_results()
        S-->>H: question_results (full)
        S-->>P: question_results (each player's own view)
    else already closed, or still waiting on answers
        DB-->>S: nothing, so stay quiet
    end
```

If the server restarts, in-memory timers are lost. To cover that, a sweep closes any overdue `OPEN` question at startup and on each connect.

## Disconnects and reconnects

```mermaid
flowchart TD
    Drop["A player's Wi-Fi drops"] --> Roster{"Are they still in the<br/>question's roster?"}
    Roster -->|"Yes. Roster = joined,<br/>not connected"| Wait["Question waits for the<br/>timer instead of closing<br/>early without them"]
    Wait --> Back["Player reconnects + sends auth"]
    Back --> Snap["Server sends a fresh<br/>session_state from MySQL"]
    Snap --> Answered{"Already answered<br/>this question?"}
    Answered -->|"yes"| Sub["Show 'answer submitted'"]
    Answered -->|"no, still open"| Choices["Show the answer buttons"]
    Answered -->|"question closed"| Res["Show last results"]

    HDrop["Host disconnects"] --> HStat["Players get host_status<br/>{connected: false}"]
    HStat --> Timers["Timers keep running;<br/>questions still close"]
    Timers --> HBack["Host reconnects, gets<br/>session_state, carries on"]
```

## What each message is

| Direction | Message | Meaning |
|---|---|---|
| any → server | `auth` | First message: "here's my login" |
| any → server | `ping` | "Still here" (every 25 s); server answers `pong` |
| host → server | `open_question` | Start the next question |
| player → server | `submit_answer` | "I picked choice 42" |
| server → one | `session_state` | Full snapshot on every connect and reconnect |
| server → all | `question_opened` | Show the question and start the countdown |
| server → host | `answer_progress` | "3 of 5 have answered" |
| server → all | `question_closed` | Time's up, with the reason |
| server → each | `question_results` | Host: everything. Player: own row + top 5 |
| server → players | `host_status` | Host connected or not |
| server → sender | `ack` / `error` | Reply to a command; errors use the same codes as the HTTP API and keep the socket open |

Planned but not in the PoC: `close_question` (host skip), `end_session`, `cancel_session`, `leave`, `participant_joined`/`participant_left` and `session_ended`. In #38 the commands answer `error: command_not_supported`.

## PR #36 — the protocol (`docs/LIVE_PROTOCOL.md`)

A docs-only PR that defines the contract above, built on top of the four merged teammate services. It covers state machines, first-message authentication, every event in both directions (reusing the existing Pydantic models and HTTP error codes), reconnect snapshots, the exactly-once close rule, host vs. player result views (the results service has no permission check of its own, so the WebSocket layer filters), close codes, implementation rules, and open questions for the next meeting:

1. Should players see top 5 + their own rank, or only their own rank? (Taha, depending on the approved screens)
2. Should abandoned sessions auto-cancel? (Proposed: not in the MVP.)
3. Should Admins be able to watch live? (Proposed: no; they see results afterwards.)
4. Can a host also play? (No; the schema already forbids it.)

**Reviewers requested:** Pronob (lifecycle/results fit), Anh (sessions/MySQL), Taha (participant view and leaderboard vs. screens).

## PR #38 — the WebSocket proof of concept

The first step of the protocol's build plan. New code lives in `backend/app/live/` (`protocol.py`, `auth.py`, `snapshot.py`, `hub.py`) and `backend/app/api/routes/live.py`.

**Design rules it follows:**

- One database session per command, run in the threadpool, closed straight after. A row lock held by a long-lived session could block everyone.
- Commit, then broadcast.
- An in-memory registry of who is connected, so the MVP runs **one uvicorn worker**. More workers would need Redis, which is out of scope.
- The REST answer route (`POST /sessions/{id}/questions/{qid}/responses`) runs the same after-answer hook as a background task, so it can't become a back door that never closes questions.

**Verification:**

- The existing suite passed: **157 tests** against MySQL.
- A manual end-to-end script (not committed) ran a real server with a host and two player clients against MySQL: **29 of 29 checks passed**. It covered every refusal code, the 4409 tab replacement, both roles' snapshots, a duplicate answer being rejected, `answer_progress` 1/2, exactly one `question_closed` per socket arriving before results, the player-view filter, reconnecting to `last_results`, host disconnect and reconnect, a deadline close at ~2.3 s on a 2 s question, a REST answer triggering the close broadcast, and a malformed message closing with 4400.

**Not included:** automated WebSocket tests (a team decision for now; the protocol's §8.5 asks for one), the not-yet-written services (`end_session`, `cancel_session`, `leave`, host force-close), and join/leave broadcasts (joining is still REST-only).

## What this unlocks next

```mermaid
flowchart LR
    A["#36 protocol<br/>+ #38 PoC"] --> B["Missing services:<br/>end_session, cancel_session,<br/>leave, close_question_now"]
    B --> C["React useLiveSession() hook:<br/>owns the socket, reconnects<br/>with backoff"]
    C --> D["Live host + player screens<br/>(from Anh's and Taha's mockups)"]
    D --> E["Results pages + Excel export"]
    E --> F["End-to-end demo + deploy"]
```
