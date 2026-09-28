function ParticipantFeedbackPage() {
  return (
    <div className="participant-page feedback-page correct-feedback">
      <div className="feedback-check">✓</div>

      <h1>Correct!</h1>

      <div className="points-earned">
        +847
      </div>

      <p className="participant-explanation">
        Queue follows FIFO ordering: the first item
        added is the first item removed.
      </p>

      <div className="feedback-stats">
        <div>
          <span>Score</span>
          <strong>2,540</strong>
        </div>

        <div>
          <span>Rank</span>
          <strong>#3</strong>
        </div>
      </div>

      <p className="waiting-message">
        Look at the host screen for the leaderboard
      </p>
    </div>
  );
}

export default ParticipantFeedbackPage;