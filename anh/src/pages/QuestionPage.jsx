import Header from "../components/Header";
import ProgressBar from "../components/ProgressBar";
import AnswerChoice from "../components/AnswerChoice";

function QuestionPage({
  selectedAnswer,
  setSelectedAnswer,
  onSubmit,
}) {
  const answers = [
    {
      id: "A",
      text: "Stack",
      shape: "▲",
      colorClass: "answer-red",
    },
    {
      id: "B",
      text: "Queue",
      shape: "◆",
      colorClass: "answer-blue",
    },
    {
      id: "C",
      text: "Binary Tree",
      shape: "●",
      colorClass: "answer-yellow",
    },
    {
      id: "D",
      text: "Hash Table",
      shape: "■",
      colorClass: "answer-green",
    },
  ];

  const handleAnswer = (answerId) => {
    setSelectedAnswer(answerId);

    // Small delay so the selected answer can be seen
    setTimeout(() => {
      onSubmit();
    }, 300);
  };

  return (
    <div className="page">
      <Header
        quizTitle="Data Structures"
        rightText="Question 3 of 10"
      />

      <main className="quiz-content">
        <ProgressBar current={3} total={10} />

        <section className="kahoot-question">
          <div className="question-top">
            <div className="timer">
              <span>32</span>
            </div>

            <div className="question-title">
              <p>QUESTION 3 OF 10</p>

              <h1>
                Which data structure follows FIFO
                (First In, First Out) ordering?
              </h1>
            </div>

            <div className="score-box">
              <span>Score</span>
              <strong>1,693</strong>
            </div>
          </div>

          <div className="kahoot-answers">
            {answers.map((answer) => (
              <AnswerChoice
                key={answer.id}
                shape={answer.shape}
                text={answer.text}
                colorClass={answer.colorClass}
                onClick={() => handleAnswer(answer.id)}
              />
            ))}
          </div>

          <div className="question-footer">
            <span>Answer before the timer runs out!</span>
            <strong>Rank #3</strong>
          </div>
        </section>
      </main>
    </div>
  );
}

export default QuestionPage;