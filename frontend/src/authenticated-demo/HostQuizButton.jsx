import { Link } from "react-router";

export default function HostQuizButton({ quiz }) {
  if (!quiz.class_id) {
    return <small>This legacy quiz does not belong to a class.</small>;
  }

  return (
    <Link
      className="cl-button"
      to={`/app/classes/${quiz.class_id}/quiz-workflow`}
    >
      Approval & hosting →
    </Link>
  );
}
