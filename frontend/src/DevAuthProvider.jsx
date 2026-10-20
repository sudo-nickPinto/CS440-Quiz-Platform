import { Auth0Context } from '@auth0/auth0-react'

const DEV_TOKEN = 'local-development-token'

const context = {
  isAuthenticated: true,
  isLoading: false,
  error: undefined,
  user: {
    sub: 'dev|local',
    email: 'developer@localhost',
    name: 'Local Developer',
    email_verified: true,
  },
  getAccessTokenSilently: async () => DEV_TOKEN,
  loginWithRedirect: async () => {},
  logout: async () => {},
}

export default function DevAuthProvider({ children }) {
  return (
    <Auth0Context.Provider value={context}>{children}</Auth0Context.Provider>
  )
}
