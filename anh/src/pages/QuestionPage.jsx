import Header from "../components/Header";
import ProgressBar from "../components/ProgressBar";
import AnswerChoice from "../components/AnswerChoice";

function QuestionPage({
  setSelectedAnswer,
  onSubmit,
}) {
  const answers = [
    {
      id: "A",
      text: "Stack",
    },
    {
      id: "B",
      text: "Queue",
    },
    {
      id: "C",
      text: "Binary Tree",
    },
    {
      id: "D",
      text: "Hash Table",
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

        <section className="quiz-question">
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

          <div className="quiz-answers">
            {answers.map((answer) => (
              <AnswerChoice
                key={answer.id}
                id={answer.id}
                text={answer.text}
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
