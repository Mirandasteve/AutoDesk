/**
 * Loads the SRS vocabularies once and shares them with every dropdown.
 *
 * The backend owns these lists (they mirror the database CHECK constraints), so
 * the UI can never offer a category or priority the API would reject.
 */
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import { metaApi } from '../services/api'

const DEFAULT_META = {
  categories: [],
  priorities: [],
  statuses: [],
  routing_table: {},
  teams: [],
  sla_hours: {},
  sla_near_threshold: 0.8,
  ticket_status_flow: ['Open', 'In Progress', 'Resolved'],
}

const MetaContext = createContext(null)

export function MetaProvider({ children }) {
  const [meta, setMeta] = useState(DEFAULT_META)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const reload = useCallback(async () => {
    setLoading(true)
    try {
      const data = await metaApi.get()
      setMeta({ ...DEFAULT_META, ...data })
      setError(null)
    } catch (err) {
      setError(err)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    reload()
  }, [reload])

  const value = useMemo(
    () => ({
      meta,
      loading,
      error,
      reload,
      categories: meta.categories,
      priorities: meta.priorities,
      statuses: meta.statuses,
      teams: meta.teams,
      routingTable: meta.routing_table,
      /** Response window in hours for each priority, from the SLA config. */
      slaHours: meta.sla_hours,
      /** Which support team handles a given category, per SRS section 7. */
      teamForCategory: (category) => meta.routing_table[category] ?? null,
    }),
    [meta, loading, error, reload],
  )

  return <MetaContext.Provider value={value}>{children}</MetaContext.Provider>
}

export function useMeta() {
  const context = useContext(MetaContext)
  if (!context) {
    throw new Error('useMeta must be used inside <MetaProvider>.')
  }
  return context
}