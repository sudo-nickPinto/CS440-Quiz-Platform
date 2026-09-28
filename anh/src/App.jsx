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
    <div className="app">
      <div className="demo-toolbar">
        <div className="view-switcher">
          <button
            className={view === "host" ? "active" : ""}
            onClick={() => setView("host")}
          >
            Host
          </button>

          <button
            className={view === "participant" ? "active" : ""}
            onClick={() => setView("participant")}
          >
            Participant
          </button>
        </div>

        {view === "host" ? (
          <div className="screen-switcher">
            <button onClick={() => setHostPage("question")}>
              Question
            </button>
            <button onClick={() => setHostPage("results")}>
              Answer Results
            </button>
            <button onClick={() => setHostPage("leaderboard")}>
              Leaderboard
            </button>
          </div>
        ) : (
          <div className="screen-switcher">
            <button onClick={() => setParticipantPage("question")}>
              Question
            </button>
            <button onClick={() => setParticipantPage("submitted")}>
              Submitted
            </button>
            <button onClick={() => setParticipantPage("feedback")}>
              Feedback
            </button>
            <button onClick={() => setParticipantPage("results")}>
              Final Results
            </button>
          </div>
        )}
      </div>

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
  );
}

export default App;