export default function RejectionFeedback({ comment, heading }) {
  if (!comment && !heading) return null;
  return (
    <span className="cl-rejection-feedback">
      <strong>{heading ?? "Rejection feedback"}</strong>
      {comment && <span>{comment}</span>}
    </span>
  );
}
