export default function RejectionFeedback({ comment }) {
  if (!comment) return null;
  return (
    <span className="cl-rejection-feedback">
      <strong>Rejection feedback</strong>
      <span>{comment}</span>
    </span>
  );
}
