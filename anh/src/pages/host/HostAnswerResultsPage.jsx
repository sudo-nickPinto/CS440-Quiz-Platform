function HostAnswerResultsPage({ onLeaderboard }) {
  const results = [
    {
      label: "A",
      answer: "Stack",
      count: 3,
    },
    {
      label: "B",
      answer: "Queue",
      count: 12,
      correct: true,
    },
    {
      label: "C",
      answer: "Binary Tree",
      count: 2,
    },
    {
      label: "D",
      answer: "Hash Table",
      count: 1,
    },
  ];

  return (
    <div className="host-page">
      <header className="host-header">
        <strong>Data Structures</strong>
        <span>Question 3 Results</span>
      </header>

      <main className="host-results-content">
        <p className="host-eyebrow">QUESTION 3</p>

        <h1>How did everyone answer?</h1>

        <p className="host-question-small">
          Which data structure follows FIFO ordering?
        </p>

        <div className="distribution">
          {results.map((result) => (
            <div className="distribution-column" key={result.answer}>
              <div className="bar-area">
                <span className="bar-number">{result.count}</span>

                <div
                  className={`distribution-bar${result.correct ? " correct" : ""}`}
                  style={{
                    height: `${result.count * 18}px`,
                  }}
                />
              </div>

              <div
                className={`distribution-label${result.correct ? " correct" : ""}`}
              >
                <span className="answer-index">{result.label}</span>

                <strong>{result.answer}</strong>

                {result.correct && (
                  <span className="correct-check">✓</span>
                )}
              </div>
            </div>
          ))}
        </div>

        <button
          className="host-next-button"
          onClick={onLeaderboard}
        >
          Show Leaderboard
        </button>
      </main>
    </div>
  );
}

export default HostAnswerResultsPage;