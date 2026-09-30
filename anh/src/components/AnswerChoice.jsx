function AnswerChoice({ id, text, onClick }) {
  return (
    <button
      className="quiz-answer"
      onClick={onClick}
    >
      <span className="answer-index">{id}</span>
      <span className="answer-text">{text}</span>
    </button>
  );
}

export default AnswerChoice;