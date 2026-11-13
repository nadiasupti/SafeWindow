import { useCallback, useEffect, useState } from 'react'

/**
 * Loads data with `fetcher` (a stable function returning a promise) and again whenever `reload()` is called.
 * Returns { data, error, reload }. `data` stays on the last good value while a reload is running or has failed.
 */
export function useLoader(fetcher) {
  const [state, setState] = useState({ data: null, error: null })
  const [tick, setTick] = useState(0)
  useEffect(() => {
    let alive = true
    fetcher().then(
      (data) => alive && setState({ data, error: null }),
      (error) => alive && setState((s) => ({ ...s, error })),
    )
    return () => {
      alive = false
    }
  }, [fetcher, tick])
  const reload = useCallback(() => setTick((n) => n + 1), [])
  return { data: state.data, error: state.error, reload }
}
