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
          <div className="host-answer answer-red">
            <span className="host-shape">▲</span>
            <span>Stack</span>
          </div>

          <div className="host-answer answer-blue">
            <span className="host-shape">◆</span>
            <span>Queue</span>
          </div>

          <div className="host-answer answer-yellow">
            <span className="host-shape">●</span>
            <span>Binary Tree</span>
          </div>

          <div className="host-answer answer-green">
            <span className="host-shape">■</span>
            <span>Hash Table</span>
          </div>
        </div>
      </main>
    </div>
  );
}

export default HostQuestionPage;