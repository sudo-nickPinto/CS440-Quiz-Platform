function AnswerChoice({ shape, text, colorClass, onClick }) {
  return (
    <button
      className={`kahoot-answer ${colorClass}`}
      onClick={onClick}
    >
      <span className="answer-shape">{shape}</span>
      <span className="answer-text">{text}</span>
    </button>
  );
}

export default AnswerChoice;