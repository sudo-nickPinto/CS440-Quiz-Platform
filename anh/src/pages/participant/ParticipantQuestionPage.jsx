function ParticipantQuestionPage({ onAnswer }) {
  return (
    <div className="participant-page participant-question-page">
      <div className="participant-top">
        <span>Question 3 of 10</span>

        <div className="participant-timer">
          32
        </div>
      </div>

      <div className="participant-shapes">
        <button
          className="participant-answer answer-red"
          onClick={() => onAnswer("A")}
          aria-label="Red triangle answer"
        >
          ▲
        </button>

        <button
          className="participant-answer answer-blue"
          onClick={() => onAnswer("B")}
          aria-label="Blue diamond answer"
        >
          ◆
        </button>

        <button
          className="participant-answer answer-yellow"
          onClick={() => onAnswer("C")}
          aria-label="Yellow circle answer"
        >
          ●
        </button>

        <button
          className="participant-answer answer-green"
          onClick={() => onAnswer("D")}
          aria-label="Green square answer"
        >
          ■
        </button>
      </div>

      <div className="participant-bottom">
        <div>
          <span>Score</span>
          <strong>1,693</strong>
        </div>

        <div>
          <span>Rank</span>
          <strong>#3</strong>
        </div>
      </div>
    </div>
  );
}

export default ParticipantQuestionPage;