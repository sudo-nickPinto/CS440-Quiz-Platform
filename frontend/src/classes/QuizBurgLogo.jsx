import "./QuizBurgLogo.css";

export default function QuizBurgLogo() {
  return (
    <span className="qb-logo" role="img" aria-label="QuizBurg">
      <span className="qb-quiz" aria-hidden="true">
        QUIZ
      </span>
      <span className="qb-burg" aria-hidden="true">
        BURG
      </span>
    </span>
  );
}
