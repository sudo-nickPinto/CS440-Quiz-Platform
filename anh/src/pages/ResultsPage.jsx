function ResultsPage({ onRestart }) {
  return (
    <div className="page">
      <header className="header">
        <div className="logo">Quiz Platform</div>
        <span>Data Structures</span>
      </header>

      <main className="content narrow">
        <section className="results-card">
          <p className="eyebrow">QUIZ COMPLETE</p>
          <h1>Great work!</h1>

          <p className="results-subtitle">
            Here's how you did on Data Structures.
          </p>

          <div className="score-circle">
            <strong>8 / 10</strong>
            <span>Correct</span>
          </div>

          <div className="result-stats">
            <div>
              <span>Final Rank</span>
              <strong>#3</strong>
            </div>

            <div>
              <span>Leaderboard Points</span>
              <strong>7,840</strong>
            </div>

            <div>
              <span>Accuracy</span>
              <strong>80%</strong>
            </div>
          </div>

          <div className="result-actions">
            <button className="secondary-button">
              Review Answers
            </button>

            <button className="primary-button" onClick={onRestart}>
              Back to Demo
            </button>
          </div>
        </section>
      </main>
    </div>
  );
}

export default ResultsPage;