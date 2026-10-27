import { Auth0Provider } from '@auth0/auth0-react'
import { useNavigate } from 'react-router'

// Sends the user back to the page they started sign-in from (see
// returnToState in api.js). Navigating through the router, rather than the
// SDK's default history.replaceState, keeps React Router's location in sync.
export default function Auth0ProviderWithNavigate({ children }) {
  const navigate = useNavigate()
  return (
    <Auth0Provider
      domain={import.meta.env.VITE_AUTH0_DOMAIN}
      clientId={import.meta.env.VITE_AUTH0_CLIENT_ID}
      cacheLocation="localstorage"
      useRefreshTokens
      authorizationParams={{
        redirect_uri: window.location.origin,
        audience: import.meta.env.VITE_AUTH0_AUDIENCE,
      }}
      onRedirectCallback={(appState) =>
        navigate(appState?.returnTo || '/', { replace: true })
      }
    >
      {children}
    </Auth0Provider>
  )
}
