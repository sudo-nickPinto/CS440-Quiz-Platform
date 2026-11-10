// Preset avatars: a figure on a colored tile, saved on the account as
// "figure.color" (e.g. "owl.sky"). backend/app/avatars.py holds the same ids
// and rejects anything else, so change both lists together.

export const AVATAR_FIGURES = [
  { id: 'owl', label: 'Owl' },
  { id: 'fox', label: 'Fox' },
  { id: 'cat', label: 'Cat' },
  { id: 'bear', label: 'Bear' },
  { id: 'frog', label: 'Frog' },
  { id: 'penguin', label: 'Penguin' },
  { id: 'robot', label: 'Robot' },
  { id: 'ghost', label: 'Ghost' },
  { id: 'cactus', label: 'Cactus' },
  { id: 'rocket', label: 'Rocket' },
  { id: 'octopus', label: 'Octopus' },
  { id: 'alien', label: 'Alien' },
]

// Each color id maps to a design token in avatar.css (.avatar-<id>).
export const AVATAR_COLORS = [
  { id: 'sky', label: 'Sky' },
  { id: 'apricot', label: 'Apricot' },
  { id: 'sand', label: 'Sand' },
  { id: 'paper', label: 'Paper' },
  { id: 'navy', label: 'Navy' },
  { id: 'orange', label: 'Orange' },
]

const FIGURE_IDS = new Set(AVATAR_FIGURES.map((figure) => figure.id))
const COLOR_IDS = new Set(AVATAR_COLORS.map((color) => color.id))

// Returns { figure, color } for a known key, or null (show initials).
export function parseAvatarKey(key) {
  if (typeof key !== 'string') return null
  const [figure, color, extra] = key.split('.')
  if (extra !== undefined || !FIGURE_IDS.has(figure) || !COLOR_IDS.has(color)) {
    return null
  }
  return { figure, color }
}

export function avatarKey(figure, color) {
  return `${figure}.${color}`
}

export function randomAvatarKey() {
  const pick = (list) => list[Math.floor(Math.random() * list.length)].id
  return avatarKey(pick(AVATAR_FIGURES), pick(AVATAR_COLORS))
}

export function figureLabel(id) {
  return AVATAR_FIGURES.find((figure) => figure.id === id)?.label ?? 'Avatar'
}

export function initialsFor(name) {
  return (name || 'User')
    .trim()
    .split(/\s+/)
    .slice(0, 2)
    .map((part) => part[0])
    .join('')
    .toUpperCase()
}
