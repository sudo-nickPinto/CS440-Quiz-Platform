import { Link } from "react-router";

// The app's main navigation, shown in the header on every page for faculty
// and students alike. Quizzes, results and sessions all live under a class,
// so Classes lights up for them too.
// Each link also lights up on the pages that live under it.
const LINKS = [
  {
    to: "/app/classes",
    label: "Classes",
    matches: (path) =>
      path.startsWith("/app/classes") ||
      path.startsWith("/app/join/class") ||
      path.startsWith("/app/quizzes") ||
      path.startsWith("/app/results"),
  },
  {
    to: "/app/join",
    label: "Join game",
    matches: (path) => path === "/app/join" || path === "/app/join/",
  },
];

export default function AppNav({ pathname }) {
  // Hidden during a live game, so nobody leaves a running session by
  // accident; the live screens have their own exits.
  if (/^\/app\/(host|play)\//.test(pathname)) return null;

  return (
    <nav className="qb-app-nav" aria-label="Main">
      {LINKS.map(({ to, label, matches }) => (
        <Link
          key={to}
          to={to}
          aria-current={matches(pathname) ? "page" : undefined}
        >
          {label}
        </Link>
      ))}
    </nav>
  );
}
