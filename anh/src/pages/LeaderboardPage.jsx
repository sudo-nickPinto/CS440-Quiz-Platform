function LeaderboardPage({ onContinue }) {
  const players = [
    { rank: 1, name: "Alex", points: 2750 },
    { rank: 2, name: "Jamie", points: 2610 },
    { rank: 3, name: "You", points: 2540, current: true },
    { rank: 4, name: "Taylor", points: 2320 },
    { rank: 5, name: "Jordan", points: 2180 },
  ];

  return (
    <div className="page">
      <header className="header">
        <div className="logo">Quiz Platform</div>
        <span>Data Structures</span>
      </header>

      <main className="content narrow">
        <section className="leaderboard-card">
          <p className="eyebrow">AFTER QUESTION 3</p>
          <h1>Leaderboard</h1>

          <div className="leaderboard">
            {players.map((player) => (
              <div
                key={player.rank}
                className={`leaderboard-row ${
                  player.current ? "current-player" : ""
                }`}
              >
                <span className="rank">{player.rank}</span>

                <span className="player-name">
                  {player.name}
                  {player.current && (
                    <small>That's you</small>
                  )}
                </span>

                <strong>
                  {player.points.toLocaleString()} pts
                </strong>
              </div>
            ))}
          </div>

          <button className="primary-button" onClick={onContinue}>
            Finish Quiz
          </button>
        </section>
      </main>
    </div>
  );
}

export default LeaderboardPage;