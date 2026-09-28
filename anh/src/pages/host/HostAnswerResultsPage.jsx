function HostAnswerResultsPage({ onLeaderboard }) {
  const results = [
    {
      shape: "▲",
      answer: "Stack",
      count: 3,
      color: "answer-red",
    },
    {
      shape: "◆",
      answer: "Queue",
      count: 12,
      color: "answer-blue",
      correct: true,
    },
    {
      shape: "●",
      answer: "Binary Tree",
      count: 2,
      color: "answer-yellow",
    },
    {
      shape: "■",
      answer: "Hash Table",
      count: 1,
      color: "answer-green",
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
                  className={`distribution-bar ${result.color}`}
                  style={{
                    height: `${result.count * 18}px`,
                  }}
                />
              </div>

              <div
                className={`distribution-label ${result.color}`}
              >
                <span>{result.shape}</span>

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