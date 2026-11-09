import { useState } from 'react'
import { useAuth0 } from '@auth0/auth0-react'
import { apiFetch } from '../api'
import Avatar from '../avatars/Avatar'
import AvatarPicker from '../avatars/AvatarPicker'
import { parseAvatarKey, randomAvatarKey } from '../avatars/catalog'
import './ProfileForm.css'

// Matches NAME_MAX_LENGTH in backend/app/accounts.py.
const NAME_MAX = 50

// Accounts made before profiles only have display_name, which is the email
// address for email signups. Only prefill from it when it looks like a name.
function initialNames(account) {
  if (account?.first_name || account?.last_name) {
    return [account.first_name ?? '', account.last_name ?? '']
  }
  const name = (account?.display_name ?? '').trim()
  if (!name || name.includes('@')) return ['', '']
  const [first, ...rest] = name.split(/\s+/)
  return [first.slice(0, NAME_MAX), rest.join(' ').slice(0, NAME_MAX)]
}

// First name, last name and avatar, saved with PATCH /me. Used by the
// one-time setup screen and the in-app Edit profile page; `children` are
// extra actions shown beside the submit button.
export default function ProfileForm({
  account,
  submitLabel,
  submitClassName,
  savedMessage = '',
  onSaved,
  children,
}) {
  const { getAccessTokenSilently } = useAuth0()
  const [firstName, setFirstName] = useState(() => initialNames(account)[0])
  const [lastName, setLastName] = useState(() => initialNames(account)[1])
  const [avatar, setAvatar] = useState(() =>
    parseAvatarKey(account?.avatar_key) ? account.avatar_key : randomAvatarKey(),
  )
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [saved, setSaved] = useState('')

  const previewName = `${firstName.trim()} ${lastName.trim()}`.trim()

  async function save(event) {
    event.preventDefault()
    if (saving) return
    setSaving(true)
    setError('')
    setSaved('')
    try {
      const updated = await apiFetch('/me', getAccessTokenSilently, {
        method: 'PATCH',
        body: JSON.stringify({
          first_name: firstName,
          last_name: lastName,
          avatar_key: avatar,
        }),
      })
      setSaving(false)
      setSaved(savedMessage)
      onSaved?.(updated)
    } catch (err) {
      setSaving(false)
      setError(err.message || 'Your profile could not be saved. Please try again.')
    }
  }

  return (
    <form className="pf" onSubmit={save} aria-busy={saving}>
      <div className="pf-preview">
        <Avatar avatarKey={avatar} name={previewName} size={72} />
        <div className="pf-preview-text">
          <p className="pf-preview-label">How others see you</p>
          <p className="pf-preview-name">{previewName || 'Your name'}</p>
        </div>
      </div>

      <fieldset className="pf-body" disabled={saving}>
        <div className="pf-names">
          <label className="pf-field">
            <span>First name</span>
            <input
              className="pf-input"
              name="first_name"
              autoComplete="given-name"
              required
              maxLength={NAME_MAX}
              value={firstName}
              onChange={(event) => setFirstName(event.target.value)}
            />
          </label>

          <label className="pf-field">
            <span>Last name</span>
            <input
              className="pf-input"
              name="last_name"
              autoComplete="family-name"
              required
              maxLength={NAME_MAX}
              value={lastName}
              onChange={(event) => setLastName(event.target.value)}
            />
          </label>
        </div>

        <AvatarPicker value={avatar} onChange={setAvatar} />
      </fieldset>

      <div className="pf-footer">
        <p className="pf-note pf-note-error" role="alert">
          {error}
        </p>
        <p className="pf-note pf-note-saved" role="status">
          {saved}
        </p>

        <div className="pf-actions">
          <button className={submitClassName} type="submit" disabled={saving}>
            <span>{saving ? 'Saving…' : submitLabel}</span>
            <span aria-hidden="true">→</span>
          </button>
          {children}
        </div>
      </div>
    </form>
  )
}
