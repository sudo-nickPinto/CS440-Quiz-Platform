import { useState } from "react";
import HostQuestionPage from "./pages/host/HostQuestionPage";
import HostAnswerResultsPage from "./pages/host/HostAnswerResultsPage";
import HostLeaderboardPage from "./pages/host/HostLeaderboardPage";

import ParticipantQuestionPage from "./pages/participant/ParticipantQuestionPage";
import ParticipantSubmittedPage from "./pages/participant/ParticipantSubmittedPage";
import ParticipantFeedbackPage from "./pages/participant/ParticipantFeedbackPage";
import ParticipantResultsPage from "./pages/participant/ParticipantResultsPage";

import "./App.css";

function App() {
  const [view, setView] = useState("host");
  const [hostPage, setHostPage] = useState("question");
  const [participantPage, setParticipantPage] = useState("question");
  const [selectedAnswer, setSelectedAnswer] = useState(null);

  const handleParticipantAnswer = (answer) => {
    setSelectedAnswer(answer);
    setParticipantPage("submitted");
  };

  return (
    <div className="app-shell">
      <header className="top">
        <div className="brand-logo">
          QUIZ<span>.</span>PLATFORM
        </div>
        <div className="user">
          <span className="name">Anh Nguyen</span>
          <div className="avatar" aria-hidden="true">AN</div>
        </div>
      </header>

      <div className="mockup-frame">
        <nav className="demo-toolbar" aria-label="Mockup screens">
          <div className="view-switcher" role="tablist" aria-label="Quiz mode">
          <button
            type="button"
            role="tab"
            aria-selected={view === "host"}
            onClick={() => setView("host")}
          >
            Presenter
          </button>

          <button
            type="button"
            role="tab"
            aria-selected={view === "participant"}
            onClick={() => setView("participant")}
          >
            Participant
          </button>
          </div>

          {view === "host" ? (
            <div className="screen-switcher" aria-label="Presenter screen">
            <button
              type="button"
              className={hostPage === "question" ? "active" : ""}
              onClick={() => setHostPage("question")}
            >
              Question
            </button>
            <button
              type="button"
              className={hostPage === "results" ? "active" : ""}
              onClick={() => setHostPage("results")}
            >
              Answer Results
            </button>
            <button
              type="button"
              className={hostPage === "leaderboard" ? "active" : ""}
              onClick={() => setHostPage("leaderboard")}
            >
              Leaderboard
            </button>
            </div>
          ) : (
            <div className="screen-switcher" aria-label="Participant screen">
            <button
              type="button"
              className={participantPage === "question" ? "active" : ""}
              onClick={() => setParticipantPage("question")}
            >
              Question
            </button>
            <button
              type="button"
              className={participantPage === "submitted" ? "active" : ""}
              onClick={() => setParticipantPage("submitted")}
            >
              Submitted
            </button>
            <button
              type="button"
              className={participantPage === "feedback" ? "active" : ""}
              onClick={() => setParticipantPage("feedback")}
            >
              Feedback
            </button>
            <button
              type="button"
              className={participantPage === "results" ? "active" : ""}
              onClick={() => setParticipantPage("results")}
            >
              Final Results
            </button>
            </div>
          )}
        </nav>

        {view === "host" && (
          <div className="host-view">
          {hostPage === "question" && <HostQuestionPage />}

          {hostPage === "results" && (
            <HostAnswerResultsPage
              onLeaderboard={() => setHostPage("leaderboard")}
            />
          )}

          {hostPage === "leaderboard" && <HostLeaderboardPage />}
          </div>
        )}

        {view === "participant" && (
          <div className="participant-view">
          <div className="phone">
            <div className="phone-screen">
              {participantPage === "question" && (
                <ParticipantQuestionPage
                  onAnswer={handleParticipantAnswer}
                />
              )}

              {participantPage === "submitted" && (
                <ParticipantSubmittedPage
                  selectedAnswer={selectedAnswer}
                />
              )}

              {participantPage === "feedback" && (
                <ParticipantFeedbackPage />
              )}

              {participantPage === "results" && (
                <ParticipantResultsPage />
              )}
            </div>
          </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default App;
