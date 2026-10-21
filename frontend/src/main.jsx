import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router'
import App from './App.jsx'
import Auth0ProviderWithNavigate from './Auth0ProviderWithNavigate.jsx'
import { hasRequiredAppConfig } from './app-config.js'
import './index.css'
import './styles/theme.css'

const authConfigured = hasRequiredAppConfig(import.meta.env)

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <BrowserRouter>
      {authConfigured ? (
        <Auth0ProviderWithNavigate>
          <App />
        </Auth0ProviderWithNavigate>
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