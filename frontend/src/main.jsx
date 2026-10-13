import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { Auth0Provider } from '@auth0/auth0-react'
import { BrowserRouter } from 'react-router'
import App from './App.jsx'
import './index.css'
import './styles/theme.css'

const authConfigured = Boolean(
  import.meta.env.VITE_AUTH0_DOMAIN &&
  import.meta.env.VITE_AUTH0_CLIENT_ID,
)

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <BrowserRouter>
      {authConfigured ? (
        <Auth0Provider
          domain={import.meta.env.VITE_AUTH0_DOMAIN}
          clientId={import.meta.env.VITE_AUTH0_CLIENT_ID}
          cacheLocation={
            import.meta.env.DEV ? 'localstorage' : 'memory'
          }
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
            background: '#f3ebe2',
            color: '#222222',
          }}
        >
          <h1>Authentication is not configured yet.</h1>
        </main>
      )}
    </BrowserRouter>
  </StrictMode>,
)