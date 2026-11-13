import { Link } from "react-router";

import { useClassesResource } from "./classResources";
import { ResourceMessage } from "./ClassUI";
import { classesForNewQuiz } from "./newQuizClasses";
import "./new-quiz-picker.css";

// /app/quizzes/new without ?class=: pick the class the quiz belongs to
// instead of sending people off to find the right "+" button.
export default function NewQuizClassPicker() {
  const resource = useClassesResource();

  if (resource.status !== "ready") {
    return (
      <section className="qp-content">
        <h1>Create a quiz</h1>
        <ResourceMessage resource={resource} />
      </section>
    );
  }

  const choices = classesForNewQuiz(resource.data);

  return (
    <section className="qp-content" aria-labelledby="new-quiz-heading">
      <h1 id="new-quiz-heading">Create a quiz</h1>

      {choices.length === 0 ? (
        <>
          <p>
            Quizzes belong to a class. Join or create a class first, then come
            back here.
          </p>
          <Link className="cl-button" to="/app/classes">
            Go to my classes
          </Link>
        </>
      ) : (
        <>
          <p>Which class is this quiz for? Only that class can use it.</p>
          <ul className="nq-picker-list">
            {choices.map((item) => (
              <li key={item.id}>
                <Link to={`/app/quizzes/new?class=${item.id}`}>
                  <strong>{item.name}</strong>
                  <span>{item.roleLabel}</span>
                </Link>
              </li>
            ))}
          </ul>
          <Link to="/app/classes">← Back to classes</Link>
        </>
      )}
    </section>
  );
}
