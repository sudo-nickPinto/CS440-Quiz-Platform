function ParticipantResultsPage() {
  return (
    <div className="participant-page final-results-page">
      <div className="trophy">★</div>

      <p className="result-eyebrow">
        QUIZ COMPLETE
      </p>

      <h1>Great job!</h1>

      <div className="final-score">
        <strong>8 / 10</strong>
        <span>Correct Answers</span>
      </div>

      <div className="final-result-stats">
        <div>
          <span>Final Rank</span>
          <strong>#3</strong>
        </div>

        <div>
          <span>Points</span>
          <strong>7,840</strong>
        </div>
      </div>

      <p className="recorded-result-note">
        Your recorded quiz result is 8 out of 10
        correct.
      </p>
    </div>
  );
}

export default ParticipantResultsPage;