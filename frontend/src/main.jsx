import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { Auth0Provider } from '@auth0/auth0-react'
import { BrowserRouter } from 'react-router'
import App from './App.jsx'
import DevAuthProvider from './DevAuthProvider.jsx'
import { hasRequiredAppConfig, isDevAuthEnabled } from './app-config.js'
import './index.css'
import './styles/theme.css'

const authConfigured = hasRequiredAppConfig(import.meta.env)
const devAuthEnabled = isDevAuthEnabled(import.meta.env)

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <BrowserRouter>
      {devAuthEnabled ? (
        <DevAuthProvider>
          <App />
        </DevAuthProvider>
      ) : authConfigured ? (
        <Auth0Provider
          domain={import.meta.env.VITE_AUTH0_DOMAIN}
          clientId={import.meta.env.VITE_AUTH0_CLIENT_ID}
          cacheLocation="localstorage"
          useRefreshTokens
          authorizationParams={{
            redirect_uri: window.location.origin,
            audience: import.meta.env.VITE_AUTH0_AUDIENCE,
          }}
        >
          <App />
        </Auth0Provider>
      ) : (
        <main
          style={{
            padding: 32,
            background: 'var(--paper)',
            color: 'var(--ink)',
          }}
        >
          <h1>Application configuration is incomplete.</h1>
          <p>
            Sign-in is unavailable until the required authentication
            and API settings are configured.
          </p>
        </main>
      )}
    </BrowserRouter>
  </StrictMode>,
)
