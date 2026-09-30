function HostQuestionPage() {
  return (
    <div className="host-page">
      <header className="host-header">
        <div>
          <strong>Data Structures</strong>
        </div>

        <div>Question 3 of 10</div>
      </header>

      <main className="host-question-content">
        <div className="host-question-top">
          <div className="host-timer">32</div>

          <h1>
            Which data structure follows FIFO
            (First In, First Out) ordering?
          </h1>

          <div className="answer-count">
            <strong>18</strong>
            <span>Answers</span>
          </div>
        </div>

        <div className="host-answers">
          <div className="host-answer">
            <span className="answer-index">A</span>
            <span>Stack</span>
          </div>

          <div className="host-answer">
            <span className="answer-index">B</span>
            <span>Queue</span>
          </div>

          <div className="host-answer">
            <span className="answer-index">C</span>
            <span>Binary Tree</span>
          </div>

          <div className="host-answer">
            <span className="answer-index">D</span>
            <span>Hash Table</span>
          </div>
        </div>
      </main>
    </div>
  );
}

export default HostQuestionPage;