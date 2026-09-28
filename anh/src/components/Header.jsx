function Header({ quizTitle = "Data Structures", rightText }) {
  return (
    <header className="header">
      <div className="logo">Quiz Platform</div>

      <div className="header-info">
        <span>{quizTitle}</span>
        {rightText && (
          <span className="question-count">{rightText}</span>
        )}
      </div>
    </header>
  );
}

export default Header;