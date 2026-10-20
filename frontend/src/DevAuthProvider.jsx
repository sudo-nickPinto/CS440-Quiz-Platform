import { Auth0Context } from '@auth0/auth0-react'

function displayName(identity) {
  return identity
    .split(/[-_]/)
    .filter(Boolean)
    .map((part) => part[0].toUpperCase() + part.slice(1))
    .join(' ')
}

export default function DevAuthProvider({ children, identity = 'developer' }) {
  const context = {
    isAuthenticated: true,
    isLoading: false,
    error: undefined,
    user: {
      sub: `dev|${identity}`,
      email: `${identity}@localhost`,
      name: displayName(identity),
      email_verified: true,
    },
    getAccessTokenSilently: async () => `local-development-token:${identity}`,
    loginWithRedirect: async () => {},
    logout: async () => {},
  }

  return (
    <Auth0Context.Provider value={context}>{children}</Auth0Context.Provider>
  )
}
