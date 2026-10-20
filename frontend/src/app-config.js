const REQUIRED_APP_CONFIG = [
  'VITE_AUTH0_DOMAIN',
  'VITE_AUTH0_CLIENT_ID',
  'VITE_AUTH0_AUDIENCE',
  'VITE_API_BASE_URL',
]

export function hasRequiredAppConfig(env) {
  return REQUIRED_APP_CONFIG.every(
    (name) =>
      typeof env[name] === 'string' &&
      env[name].trim().length > 0,
  )
}

export function isDevAuthEnabled(env) {
  return (
    env.DEV === true &&
    env.VITE_DEV_AUTH_BYPASS === 'true' &&
    getDevAuthIdentity(env) !== null
  )
}

export function getDevAuthIdentity(env) {
  const configured = env.VITE_DEV_AUTH_USER
  const identity = (configured === undefined ? 'developer' : configured)
    .trim()
    .toLowerCase()
  return /^[a-z0-9][a-z0-9_-]{0,31}$/.test(identity) ? identity : null
}
