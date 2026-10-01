import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { Auth0Provider } from '@auth0/auth0-react'
import './index.css'
import App from './App.jsx'

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <Auth0Provider
      domain={import.meta.env.VITE_AUTH0_DOMAIN}
      clientId={import.meta.env.VITE_AUTH0_CLIENT_ID}
      // On localhost Auth0 always demands consent, so the silent re-login
      // after a refresh can never succeed. In dev only, keep the session in
      // localStorage so reloads work; production keeps tokens in memory.
      cacheLocation={import.meta.env.DEV ? 'localstorage' : 'memory'}
      authorizationParams={{
        redirect_uri: window.location.origin,
        audience: import.meta.env.VITE_AUTH0_AUDIENCE,
      }}
    >
      <App />
    </Auth0Provider>
  </StrictMode>,
)
