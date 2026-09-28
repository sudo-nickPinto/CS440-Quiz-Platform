function FeedbackPage({ selectedAnswer, onContinue }) {
  const correctAnswer = "B";
  const isCorrect = selectedAnswer === correctAnswer;

  return (
    <div className="page">
      <header className="header">
        <div className="logo">Quiz Platform</div>
        <span>Data Structures</span>
      </header>

      <main className="content narrow">
        <section className="feedback-card">
          <div
            className={`feedback-icon ${
              isCorrect ? "correct" : "incorrect"
            }`}
          >
            {isCorrect ? "✓" : "×"}
          </div>

          <p className="eyebrow">QUESTION 3 OF 10</p>

          <h1>{isCorrect ? "Correct!" : "Not quite"}</h1>

          <p className="feedback-subtitle">
            {isCorrect
              ? "Nice work. You selected the correct answer."
              : "Your answer was incorrect. Here's the correct answer."}
          </p>

          <div className="feedback-details">
            <div>
              <span className="detail-label">Your answer</span>
              <strong>
                {selectedAnswer === "A"
                  ? "A. Stack"
                  : selectedAnswer === "B"
                  ? "B. Queue"
                  : selectedAnswer === "C"
                  ? "C. Binary Tree"
                  : "D. Hash Table"}
              </strong>
            </div>

            <div>
              <span className="detail-label">Correct answer</span>
              <strong>B. Queue</strong>
            </div>
          </div>

          <div className="explanation">
            <span className="detail-label">Explanation</span>

            <p>
              A queue follows FIFO ordering. The first element added
              to the queue is the first element removed.
            </p>
          </div>

          <div className="points">
            <span>Points earned</span>
            <strong>{isCorrect ? "+847" : "+0"}</strong>
          </div>

          <button className="primary-button" onClick={onContinue}>
            View Leaderboard
          </button>
        </section>
      </main>
    </div>
  );
}

export default FeedbackPage;