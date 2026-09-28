function ProgressBar({ current, total }) {
  const percentage = (current / total) * 100;

  return (
    <div className="progress">
      <div
        className="progress-fill"
        style={{ width: `${percentage}%` }}
      />
    </div>
  );
}

export default ProgressBar;