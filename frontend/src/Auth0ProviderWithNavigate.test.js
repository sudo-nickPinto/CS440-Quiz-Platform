import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { navigate, Auth0Provider } = vi.hoisted(() => ({
  navigate: vi.fn(),
  Auth0Provider: function Auth0Provider() {},
}))

vi.mock('@auth0/auth0-react', () => ({ Auth0Provider }))
vi.mock('react-router', () => ({ useNavigate: () => navigate }))

import Auth0ProviderWithNavigate from './Auth0ProviderWithNavigate.jsx'
import { returnToState } from './api.js'

describe('Auth0ProviderWithNavigate', () => {
  beforeEach(() => {
    vi.stubEnv('VITE_AUTH0_DOMAIN', 'tenant.example.auth0.com')
    vi.stubEnv('VITE_AUTH0_CLIENT_ID', 'client-123')
    vi.stubEnv('VITE_AUTH0_AUDIENCE', 'https://quiz-platform-api')
    vi.stubGlobal('window', {
      location: {
        origin: 'https://quiz.test',
        pathname: '/app/classes/7',
        search: '?tab=students',
      },
    })
    navigate.mockClear()
  })

  afterEach(() => {
    vi.unstubAllEnvs()
    vi.unstubAllGlobals()
  })

  // The component only wires props, so calling it shows what Auth0 gets.
  function render() {
    return Auth0ProviderWithNavigate({ children: 'the app' })
  }

  it('keeps sessions across reloads with rotating refresh tokens', () => {
    const { type, props } = render()

    expect(type).toBe(Auth0Provider)
    expect(props).toMatchObject({
      domain: 'tenant.example.auth0.com',
      clientId: 'client-123',
      cacheLocation: 'localstorage',
      useRefreshTokens: true,
      authorizationParams: {
        redirect_uri: 'https://quiz.test',
        audience: 'https://quiz-platform-api',
      },
      children: 'the app',
    })
  })

  it('returns to the page sign-in started from, through the router', () => {
    // AccountGate and the landing page send returnToState() as appState;
    // Auth0 hands it back to onRedirectCallback after the redirect.
    const appState = returnToState()
    render().props.onRedirectCallback(appState)

    expect(navigate).toHaveBeenCalledExactlyOnceWith(
      '/app/classes/7?tab=students',
      { replace: true },
    )
  })

  it('goes home when there is nowhere to return to', () => {
    const { onRedirectCallback } = render().props

    onRedirectCallback(undefined)
    onRedirectCallback({})

    expect(navigate.mock.calls).toEqual([
      ['/', { replace: true }],
      ['/', { replace: true }],
    ])
  })
})
