function ParticipantSubmittedPage() {
  return (
    <div className="participant-page submitted-page">
      <h1>Answer submitted!</h1>

      <p>
        Waiting for everyone else to answer...
      </p>

      <div className="waiting-dots">
        <span />
        <span />
        <span />
      </div>
    </div>
  );
}

export default ParticipantSubmittedPage;