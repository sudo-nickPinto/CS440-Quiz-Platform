import AvatarFigure from './figures'
import { initialsFor, parseAvatarKey } from './catalog'
import './avatar.css'

// A preset avatar tile, or the person's initials when they haven't picked one.
// Decorative by default because a name is almost always shown next to it;
// pass `label` when the avatar stands alone.
export default function Avatar({ avatarKey, name, size, label, className = '' }) {
  const parsed = parseAvatarKey(avatarKey)
  const classes = [
    'avatar',
    parsed ? `avatar-${parsed.color}` : 'avatar-initials',
    className,
  ]
    .filter(Boolean)
    .join(' ')
  const style =
    size === undefined
      ? undefined
      : { '--avatar-size': typeof size === 'number' ? `${size}px` : size }
  const a11y = label ? { role: 'img', 'aria-label': label } : { 'aria-hidden': true }

  return (
    <span className={classes} style={style} {...a11y}>
      {parsed ? (
        <AvatarFigure figure={parsed.figure} />
      ) : (
        <span className="avatar-initials-text">{initialsFor(name)}</span>
      )}
    </span>
  )
}
