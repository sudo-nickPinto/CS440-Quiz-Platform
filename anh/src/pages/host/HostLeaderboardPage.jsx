function HostLeaderboardPage() {
  const players = [
    { rank: 1, name: "Alex", score: 2750 },
    { rank: 2, name: "Jamie", score: 2610 },
    { rank: 3, name: "Anh", score: 2540 },
    { rank: 4, name: "Taylor", score: 2320 },
    { rank: 5, name: "Jordan", score: 2180 },
  ];

  return (
    <div className="host-page leaderboard-host-page">
      <header className="host-header">
        <strong>Data Structures</strong>
        <span>Question 3 of 10</span>
      </header>

      <main className="host-leaderboard-content">
        <p className="host-eyebrow light">
          AFTER QUESTION 3
        </p>

        <h1>Leaderboard</h1>

        <div className="host-leaderboard">
          {players.map((player) => (
            <div
              className="host-leaderboard-row"
              key={player.rank}
            >
              <span className="leaderboard-rank">
                {player.rank}
              </span>

              <strong>{player.name}</strong>

              <span>
                {player.score.toLocaleString()} pts
              </span>
            </div>
          ))}
        </div>

        <button className="leaderboard-next-button">
          Next Question
        </button>
      </main>
    </div>
  );
}

export default HostLeaderboardPage;