import { useState, useEffect, useCallback, useRef } from 'react'
import { get } from '../api/client.js'

export default function useApi(path, params, options = {}) {
  const { pollInterval = 0 } = options
  const [data, setData]       = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError]     = useState(null)
  const timerRef              = useRef(null)

  const fetch = useCallback(async () => {
    setLoading(true)
    try {
      const result = await get(path, params)
      setData(result)
      setError(null)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }, [path, JSON.stringify(params)])

  useEffect(() => {
    fetch()
    if (pollInterval > 0) {
      timerRef.current = setInterval(fetch, pollInterval)
    }
    return () => clearInterval(timerRef.current)
  }, [fetch, pollInterval])

  return { data, loading, error, refetch: fetch }
}