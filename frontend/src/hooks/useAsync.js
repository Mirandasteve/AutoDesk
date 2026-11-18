import { useCallback, useEffect, useState } from 'react'

/**
 * Run an async loader and expose { data, loading, error, reload }.
 *
 * Guards against setting state after unmount, and against a slow first request
 * overwriting a newer one when the user re-filters quickly.
 */
export function useAsync(loader, deps = []) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [requestId, setRequestId] = useState(0)

  const run = useCallback(async () => {
    const id = requestId + 1
    setRequestId(id)
    setLoading(true)
    try {
      const result = await loader()
      if (id === requestId + 1) {
        setData(result)
        setError(null)
      }
    } catch (err) {
      if (id === requestId + 1) {
        setError(err)
      }
    } finally {
      if (id === requestId + 1) {
        setLoading(false)
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps)

  useEffect(() => {
    let cancelled = false
    async function execute() {
      setLoading(true)
      try {
        const result = await loader()
        if (!cancelled) {
          setData(result)
          setError(null)
        }
      } catch (err) {
        if (!cancelled) setError(err)
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    execute()
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps)

  return { data, loading, error, reload: run, setData }
}

/** Debounce a rapidly changing value (search boxes). */
export function useDebounced(value, delay = 350) {
  const [debounced, setDebounced] = useState(value)

  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delay)
    return () => clearTimeout(timer)
  }, [value, delay])

  return debounced
}