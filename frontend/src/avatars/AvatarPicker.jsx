import Avatar from './Avatar'
import {
  AVATAR_COLORS,
  AVATAR_FIGURES,
  avatarKey,
  parseAvatarKey,
} from './catalog'

// Two native radio groups (figure, then tile color), so arrow keys move
// through each group and screen readers announce "Owl, 1 of 12".
export default function AvatarPicker({ value, onChange, name = 'avatar' }) {
  const current = parseAvatarKey(value) ?? {
    figure: AVATAR_FIGURES[0].id,
    color: AVATAR_COLORS[0].id,
  }

  return (
    <div className="avatar-picker">
      <fieldset className="avatar-group">
        <legend>Figure</legend>
        <div className="avatar-figures">
          {AVATAR_FIGURES.map((figure) => (
            <label className="avatar-option" key={figure.id}>
              <input
                className="avatar-radio"
                type="radio"
                name={`${name}-figure`}
                value={figure.id}
                checked={current.figure === figure.id}
                onChange={() => onChange(avatarKey(figure.id, current.color))}
              />
              <Avatar
                className="avatar-option-tile"
                avatarKey={avatarKey(figure.id, current.color)}
              />
              <span className="avatar-check" aria-hidden="true">
                ✓
              </span>
              <span className="avatar-sr">{figure.label}</span>
            </label>
          ))}
        </div>
      </fieldset>

      <fieldset className="avatar-group">
        <legend>Tile color</legend>
        <div className="avatar-colors">
          {AVATAR_COLORS.map((color) => (
            <label className="avatar-option" key={color.id}>
              <input
                className="avatar-radio"
                type="radio"
                name={`${name}-color`}
                value={color.id}
                checked={current.color === color.id}
                onChange={() => onChange(avatarKey(current.figure, color.id))}
              />
              <span className={`avatar-swatch avatar-${color.id}`} />
              <span className="avatar-check" aria-hidden="true">
                ✓
              </span>
              <span className="avatar-sr">{color.label}</span>
            </label>
          ))}
        </div>
      </fieldset>
    </div>
  )
}
