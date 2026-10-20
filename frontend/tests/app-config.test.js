import assert from 'node:assert/strict'
import test from 'node:test'
import {
  getDevAuthIdentity,
  hasRequiredAppConfig,
  isDevAuthEnabled,
} from '../src/app-config.js'

const completeConfig = {
  VITE_AUTH0_DOMAIN: 'tenant.example.auth0.com',
  VITE_AUTH0_CLIENT_ID: 'test-client-id',
  VITE_AUTH0_AUDIENCE: 'https://quiz-platform-api',
  VITE_API_BASE_URL: 'http://127.0.0.1:8001',
}

test('accepts a complete configuration', () => {
  assert.equal(hasRequiredAppConfig(completeConfig), true)
})

for (const name of Object.keys(completeConfig)) {
  test(`rejects configuration without ${name}`, () => {
    const env = { ...completeConfig }
    delete env[name]

    assert.equal(hasRequiredAppConfig(env), false)
  })

  test(`rejects an empty ${name}`, () => {
    const env = { ...completeConfig, [name]: '' }

    assert.equal(hasRequiredAppConfig(env), false)
  })

  test(`rejects a whitespace-only ${name}`, () => {
    const env = { ...completeConfig, [name]: '   ' }

    assert.equal(hasRequiredAppConfig(env), false)
  })
}

test('enables local auth only in the Vite development environment', () => {
  assert.equal(
    isDevAuthEnabled({ DEV: true, VITE_DEV_AUTH_BYPASS: 'true' }),
    true,
  )
  assert.equal(
    isDevAuthEnabled({ DEV: false, VITE_DEV_AUTH_BYPASS: 'true' }),
    false,
  )
  assert.equal(
    isDevAuthEnabled({ DEV: true, VITE_DEV_AUTH_BYPASS: 'false' }),
    false,
  )
})

test('normalizes a named local development identity', () => {
  assert.equal(getDevAuthIdentity({ VITE_DEV_AUTH_USER: ' Alice ' }), 'alice')
  assert.equal(getDevAuthIdentity({}), 'developer')
})

for (const identity of ['', 'two words', '../../admin', 'a'.repeat(33)]) {
  test(`rejects invalid local development identity ${JSON.stringify(identity)}`, () => {
    assert.equal(getDevAuthIdentity({ VITE_DEV_AUTH_USER: identity }), null)
    assert.equal(
      isDevAuthEnabled({
        DEV: true,
        VITE_DEV_AUTH_BYPASS: 'true',
        VITE_DEV_AUTH_USER: identity,
      }),
      false,
    )
  })
}
