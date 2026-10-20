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
  return env.DEV === true && env.VITE_DEV_AUTH_BYPASS === 'true'
}
