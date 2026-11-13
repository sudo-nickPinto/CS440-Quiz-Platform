import { useCallback, useEffect, useRef, useState } from 'react'
import { useAuth0 } from '@auth0/auth0-react'
import { apiFetch } from '../api'

export function useApi() {
  const { getAccessTokenSilently } = useAuth0()

  return useCallback(
    (path, options) => apiFetch(path, getAccessTokenSilently, options),
    [getAccessTokenSilently],
  )
}

export function useResource(path, pollMs = 0) {
  const api = useApi()
  const [request, setRequest] = useState({ revision: 0, preserveData: false })
  const key = `${path}:${request.revision}`

  const [result, setResult] = useState({
    key: null,
    path: null,
    data: null,
    error: null,
  })

  const reload = useCallback(
    () =>
      setRequest((value) => ({
        revision: value.revision + 1,
        preserveData: false,
      })),
    [],
  )

  // Opt-in background refresh: keep the already-rendered resource visible
  // while its authoritative replacement is loading. Ordinary reload callers
  // retain the original loading-state behavior.
  const refresh = useCallback(
    () =>
      setRequest((value) => ({
        revision: value.revision + 1,
        preserveData: true,
      })),
    [],
  )

  useEffect(() => {
    if (!path) return

    const controller = new AbortController()
    let timer

    async function load() {
      let keepPolling = true

      try {
        const data = await api(path, {
          signal: controller.signal,
        })

        if (!controller.signal.aborted) {
          setResult({ key, path, data, error: null })
        }
      } catch (error) {
        if (!controller.signal.aborted) {
          setResult({ key, path, data: null, error })
        }

        if (error.status >= 400 && error.status < 500) {
          keepPolling = false
        }

        if (error.error) {
          keepPolling = false
        }
      } finally {
        if (
          !controller.signal.aborted &&
          pollMs > 0 &&
          keepPolling
        ) {
          timer = window.setTimeout(load, pollMs)
        }
      }
    }

    void load()

    return () => {
      controller.abort()
      window.clearTimeout(timer)
    }
  }, [api, path, key, pollMs])

  const current = path && result.key === key
  const previousForPath =
    request.preserveData && path && result.path === path && result.data
  const refreshing = Boolean(path) && !current && Boolean(previousForPath)

  return {
    data: current ? result.data : previousForPath || null,
    error: current ? result.error : null,
    loading: Boolean(path) && !current && !previousForPath,
    refreshing,
    reload,
    refresh,
  }
}

export function useAction() {
  const locked = useRef(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const clearError = useCallback(() => setError(null), [])

  async function run(action) {
    if (locked.current) return null

    locked.current = true
    setBusy(true)
    setError(null)

    try {
      return await action()
    } catch (failure) {
      setError(failure)
      return null
    } finally {
      locked.current = false
      setBusy(false)
    }
  }

  return { run, busy, error, clearError }
}
