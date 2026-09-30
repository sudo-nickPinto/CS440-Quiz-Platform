function ParticipantQuestionPage({ onAnswer }) {
  return (
    <div className="participant-page participant-question-page">
      <div className="participant-top">
        <span>Question 3 of 10</span>

        <div className="participant-timer">
          32
        </div>
      </div>

      <div className="participant-answers">
        <button
          className="participant-answer"
          onClick={() => onAnswer("A")}
        >
          A
        </button>

        <button
          className="participant-answer"
          onClick={() => onAnswer("B")}
        >
          B
        </button>

        <button
          className="participant-answer"
          onClick={() => onAnswer("C")}
        >
          C
        </button>

        <button
          className="participant-answer"
          onClick={() => onAnswer("D")}
        >
          D
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