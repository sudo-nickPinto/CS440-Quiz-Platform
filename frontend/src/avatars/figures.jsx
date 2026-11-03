// Original line-art figures for the preset avatars, drawn on a 64x64 grid.
// Colors come from avatar.css: .af is the figure's body, .aa an accent, .ad a
// dark detail, .ae an eye on that dark detail, .ai solid ink (eyes, noses),
// and .ns drops the outline.

const SHAPES = {
  owl: (
    <>
      <path
        className="af"
        d="M16 22 L13 9 L24 16 Q32 13 40 16 L51 9 L48 22 Q54 32 50 44 Q44 56 32 56 Q20 56 14 44 Q10 32 16 22 Z"
      />
      <circle className="af" cx="24" cy="29" r="7" />
      <circle className="af" cx="40" cy="29" r="7" />
      <circle className="ai" cx="25" cy="29" r="3" />
      <circle className="ai" cx="39" cy="29" r="3" />
      <path className="aa" d="M29 36 L35 36 L32 42 Z" />
      <path d="M24 48 Q28 51 32 48 Q36 51 40 48" />
    </>
  ),
  fox: (
    <>
      <path
        className="af"
        d="M12 6 L25 20 L39 20 L52 6 L51 30 Q48 46 32 55 Q16 46 13 30 Z"
      />
      <path className="aa" d="M16 14 L22 21 L17 26 Z" />
      <path className="aa" d="M48 14 L42 21 L47 26 Z" />
      <circle className="ai" cx="24" cy="32" r="2.75" />
      <circle className="ai" cx="40" cy="32" r="2.75" />
      <path d="M20 39 L32 50 L44 39" />
      <path className="ai" d="M28.5 45 L35.5 45 L32 49 Z" />
    </>
  ),
  cat: (
    <>
      <path
        className="af"
        d="M14 26 L14 9 L26 18 Q32 16 38 18 L50 9 L50 26 Q54 36 50 46 Q44 56 32 56 Q20 56 14 46 Q10 36 14 26 Z"
      />
      <ellipse className="ai" cx="24" cy="33" rx="2.5" ry="4" />
      <ellipse className="ai" cx="40" cy="33" rx="2.5" ry="4" />
      <path className="aa" d="M29 40 L35 40 L32 43.5 Z" />
      <path d="M32 43.5 Q29.5 47.5 26 45.5 M32 43.5 Q34.5 47.5 38 45.5" />
      <path d="M5 38 L18 40 M5 45 L18 44 M59 38 L46 40 M59 45 L46 44" />
    </>
  ),
  bear: (
    <>
      <circle className="af" cx="17" cy="18" r="7.5" />
      <circle className="af" cx="47" cy="18" r="7.5" />
      <circle className="aa ns" cx="17" cy="18" r="3.5" />
      <circle className="aa ns" cx="47" cy="18" r="3.5" />
      <circle className="af" cx="32" cy="35" r="20" />
      <circle className="ai" cx="24" cy="30" r="2.75" />
      <circle className="ai" cx="40" cy="30" r="2.75" />
      <ellipse className="aa" cx="32" cy="42" rx="9.5" ry="7.5" />
      <ellipse className="ai" cx="32" cy="38.5" rx="3.75" ry="2.75" />
      <path d="M32 41 L32 44.5 M28 46 Q32 48.5 36 46" />
    </>
  ),
  frog: (
    <>
      <path
        className="af"
        d="M8 39 Q8 25 22 26 L42 26 Q56 25 56 39 Q56 54 32 54 Q8 54 8 39 Z"
      />
      <circle className="af" cx="20" cy="20" r="9" />
      <circle className="af" cx="44" cy="20" r="9" />
      <circle className="ai" cx="20" cy="20" r="3.75" />
      <circle className="ai" cx="44" cy="20" r="3.75" />
      <circle className="aa ns" cx="16" cy="43" r="3.5" />
      <circle className="aa ns" cx="48" cy="43" r="3.5" />
      <path d="M20 39 Q32 49 44 39" />
    </>
  ),
  penguin: (
    <>
      <path
        className="ad"
        d="M32 7 Q52 7 52 32 L52 47 Q52 56 32 56 Q12 56 12 47 L12 32 Q12 7 32 7 Z"
      />
      <path
        className="af"
        d="M32 19 Q44 15 46 30 Q48 51 32 52 Q16 51 18 30 Q20 15 32 19 Z"
      />
      <circle className="ai" cx="26" cy="29" r="2.75" />
      <circle className="ai" cx="38" cy="29" r="2.75" />
      <path className="aa" d="M27.5 34 L36.5 34 L32 40.5 Z" />
    </>
  ),
  robot: (
    <>
      <path d="M32 9 L32 16" />
      <circle className="aa" cx="32" cy="8" r="3.75" />
      <rect className="af" x="8" y="28" width="6" height="12" />
      <rect className="af" x="50" y="28" width="6" height="12" />
      <rect className="af" x="14" y="16" width="36" height="36" />
      <rect className="ad" x="20" y="23" width="24" height="13" />
      <circle className="ae" cx="27" cy="29.5" r="3" />
      <circle className="ae" cx="37" cy="29.5" r="3" />
      <rect className="aa" x="23" y="41" width="18" height="6" />
      <path d="M29 41 L29 47 M35 41 L35 47" />
    </>
  ),
  ghost: (
    <>
      <path
        className="af"
        d="M14 54 L14 28 Q14 10 32 10 Q50 10 50 28 L50 54 L44 49 L38 54 L32 49 L26 54 L20 49 Z"
      />
      <ellipse className="ai" cx="25.5" cy="28" rx="3" ry="4.5" />
      <ellipse className="ai" cx="38.5" cy="28" rx="3" ry="4.5" />
      <circle className="aa ns" cx="20" cy="36" r="3" />
      <circle className="aa ns" cx="44" cy="36" r="3" />
      <ellipse className="ai" cx="32" cy="39" rx="3" ry="3.75" />
    </>
  ),
  cactus: (
    <>
      <path
        className="af"
        d="M26 31 L19 31 Q14 31 14 26 L14 19 Q14 15.5 17 15.5 Q20 15.5 20 19 L20 25 L26 25"
      />
      <path
        className="af"
        d="M38 27 L45 27 Q50 27 50 22 L50 15 Q50 11.5 47 11.5 Q44 11.5 44 15 L44 21 L38 21"
      />
      <path className="af" d="M26 42 L26 15 Q26 8 32 8 Q38 8 38 15 L38 42 Z" />
      <circle className="ai" cx="29.5" cy="24" r="1.9" />
      <circle className="ai" cx="34.5" cy="24" r="1.9" />
      <path d="M29.5 29 Q32 31.5 34.5 29" />
      <path className="aa" d="M20 46 L44 46 L41 57 L23 57 Z" />
      <rect className="aa" x="17" y="40" width="30" height="7" />
    </>
  ),
  rocket: (
    <>
      <path className="aa" d="M27 48 L32 58 L37 48 Z" />
      <path className="aa" d="M22 34 L13 49 L22 47 Z" />
      <path className="aa" d="M42 34 L51 49 L42 47 Z" />
      <path
        className="af"
        d="M32 5 Q45 15 43 34 L42 49 L22 49 L21 34 Q19 15 32 5 Z"
      />
      <circle className="ad" cx="32" cy="26" r="6.5" />
      <path d="M24 41 L40 41" />
    </>
  ),
  octopus: (
    <>
      <path
        className="af"
        d="M15 36 Q12 12 32 10 Q52 12 49 36 Q49 44 55 50 Q49 54 44 46 Q44 54 38 56 Q37 50 35 46 Q33 54 29 56 Q27 50 29 46 Q26 54 20 56 Q20 50 20 46 Q15 54 9 50 Q15 44 15 36 Z"
      />
      <circle className="ai" cx="25" cy="31" r="3" />
      <circle className="ai" cx="39" cy="31" r="3" />
      <circle className="aa ns" cx="20" cy="38" r="3" />
      <circle className="aa ns" cx="44" cy="38" r="3" />
      <path d="M28 39 Q32 42 36 39" />
    </>
  ),
  alien: (
    <>
      <path d="M24 15 L18 7 M40 15 L46 7" />
      <circle className="aa" cx="17" cy="6.5" r="3.5" />
      <circle className="aa" cx="47" cy="6.5" r="3.5" />
      <path
        className="af"
        d="M32 12 Q54 12 52 32 Q50 50 32 56 Q14 50 12 32 Q10 12 32 12 Z"
      />
      <ellipse
        className="ai"
        cx="23.5"
        cy="32"
        rx="5"
        ry="7.5"
        transform="rotate(-25 23.5 32)"
      />
      <ellipse
        className="ai"
        cx="40.5"
        cy="32"
        rx="5"
        ry="7.5"
        transform="rotate(25 40.5 32)"
      />
      <circle className="af ns" cx="21.5" cy="29" r="1.6" />
      <circle className="af ns" cx="38.5" cy="29" r="1.6" />
      <path d="M28 46 Q32 48.5 36 46" />
    </>
  ),
}

export default function AvatarFigure({ figure }) {
  return (
    <svg viewBox="0 0 64 64" aria-hidden="true" focusable="false">
      {SHAPES[figure]}
    </svg>
  )
}
