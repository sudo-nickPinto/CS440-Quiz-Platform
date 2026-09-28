function ParticipantSubmittedPage({ selectedAnswer }) {
  const answers = {
    A: {
      shape: "▲",
      color: "answer-red",
    },
    B: {
      shape: "◆",
      color: "answer-blue",
    },
    C: {
      shape: "●",
      color: "answer-yellow",
    },
    D: {
      shape: "■",
      color: "answer-green",
    },
  };

  const selected = answers[selectedAnswer] || answers.B;

  return (
    <div className="participant-page submitted-page">
      <div
        className={`submitted-shape ${selected.color}`}
      >
        {selected.shape}
      </div>

      <h1>Answer submitted!</h1>

      <p>
        Waiting for everyone else to answer...
      </p>

      <div className="waiting-dots">
        <span />
        <span />
        <span />
      </div>
    </div>
  );
}

export default ParticipantSubmittedPage;