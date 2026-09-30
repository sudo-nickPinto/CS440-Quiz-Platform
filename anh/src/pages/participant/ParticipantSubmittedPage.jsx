function ParticipantSubmittedPage({ selectedAnswer }) {
  return (
    <div className="participant-page submitted-page">
      <div className="submitted-choice" aria-label={`Answer ${selectedAnswer || "B"} selected`}>
        Answer {selectedAnswer || "B"}
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