import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { Auth0Provider } from '@auth0/auth0-react'
import { BrowserRouter, Route, Routes } from 'react-router'
import App from './App.jsx'
import DashboardPage from './components/DashboardPage'
import './index.css'
import './styles/theme.css'

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <BrowserRouter>
      <Routes>
        {import.meta.env.DEV && (
          <Route
            path="/preview/dashboard/:view"
            element={<DashboardPage preview />}
          />
        )}

        <Route
          path="*"
          element={
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
          }
        />
      </Routes>
    </BrowserRouter>
  </StrictMode>,
)