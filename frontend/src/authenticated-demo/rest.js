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
  const [revision, setRevision] = useState(0)
  const key = `${path}:${revision}`

  const [result, setResult] = useState({
    key: null,
    data: null,
    error: null,
  })

  const reload = useCallback(
    () => setRevision((value) => value + 1),
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
          setResult({ key, data, error: null })
        }
      } catch (error) {
        if (!controller.signal.aborted) {
          setResult({ key, data: null, error })
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

  return {
    data: current ? result.data : null,
    error: current ? result.error : null,
    loading: Boolean(path) && !current,
    reload,
  }
}

export function useAction() {
  const locked = useRef(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

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

  return { run, busy, error }
}