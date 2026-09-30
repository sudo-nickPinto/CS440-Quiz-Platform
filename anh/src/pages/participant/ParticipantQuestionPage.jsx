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
          <span className="answer-index">A</span>
          <span>Stack</span>
        </button>

        <button
          className="participant-answer"
          onClick={() => onAnswer("B")}
        >
          <span className="answer-index">B</span>
          <span>Queue</span>
        </button>

        <button
          className="participant-answer"
          onClick={() => onAnswer("C")}
        >
          <span className="answer-index">C</span>
          <span>Binary Tree</span>
        </button>

        <button
          className="participant-answer"
          onClick={() => onAnswer("D")}
        >
          <span className="answer-index">D</span>
          <span>Hash Table</span>
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