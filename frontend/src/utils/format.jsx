/**
 * Small presentational helpers shared across the three portals.
 *
 * The colour maps are keyed by the SRS vocabulary. Anything the API adds that
 * this file has not seen falls back to a neutral style, so a new priority or
 * status can never render as blank.
 */

export const PRIORITY_ORDER = ['Critical', 'High', 'Medium', 'Low']

export const priorityClass = {
  Critical: 'badge-critical',
  High: 'badge-high',
  Medium: 'badge-medium',
  Low: 'badge-low',
}

export const statusClass = {
  Open: 'badge-open',
  'In Progress': 'badge-in-progress',
  Resolved: 'badge-resolved',
}

export function PriorityBadge({ value }) {
  if (!value) return null
  return <span className={`badge ${priorityClass[value] ?? 'badge-low'}`}>{value}</span>
}

export function StatusBadge({ value }) {
  if (!value) return null
  return <span className={`badge ${statusClass[value] ?? 'badge-open'}`}>{value}</span>
}

export function CategoryBadge({ value }) {
  if (!value) return null
  return <span className="badge badge-category">{value}</span>
}

/**
 * SLA chip.
 *
 * The backend owns the whole computation (`sla_service.compute_sla_status`) and
 * flattens the result onto the ticket payload as `sla_status`,
 * `sla_hours`, `sla_remaining_hours` and `sla_breached`. This component only
 * reflects those values, so the UI can never disagree with the SLA report.
 */
export const SLA_STATUS = {
  WITHIN: 'Within SLA',
  NEAR: 'Near SLA',
  BREACHED: 'SLA Breached',
  RESOLVED_WITHIN: 'Resolved Within SLA',
  RESOLVED_AFTER: 'Resolved After SLA',
  PENDING: 'Pending',
}

export function SlaBadge({ ticket }) {
  if (!ticket?.sla_status) return null

  switch (ticket.sla_status) {
    case SLA_STATUS.BREACHED:
    case SLA_STATUS.RESOLVED_AFTER:
      return <span className="badge badge-breached">SLA breached</span>
    case SLA_STATUS.NEAR:
      return (
        <span className="badge badge-near">SLA due in {formatHours(ticket.sla_remaining_hours)}</span>
      )
    case SLA_STATUS.RESOLVED_WITHIN:
      return <span className="badge badge-ok">Resolved within SLA</span>
    case SLA_STATUS.PENDING:
      return null
    default:
      return <span className="badge badge-ok">Within SLA</span>
  }
}

/**
 * Notification types.
 *
 * These keys are the exact `Notification.NOTIFICATION_TYPES` tuple from the
 * backend model. An earlier version of the UI used a different vocabulary
 * (`assignment`, `status_change`, ...), so every real notification silently
 * rendered as the grey fallback; keeping the map here stops that drifting again.
 */
export const notificationTypeClass = {
  ticket_created: 'badge-ticket_created',
  ticket_assigned: 'badge-ticket_assigned',
  ticket_status: 'badge-ticket_status',
  ticket_resolved: 'badge-ticket_resolved',
  sla_warning: 'badge-sla_warning',
  sla_breach: 'badge-sla_breach',
}

export const NOTIFICATION_TYPE_LABEL = {
  ticket_created: 'Created',
  ticket_assigned: 'Assigned',
  ticket_status: 'Status change',
  ticket_resolved: 'Resolved',
  sla_warning: 'SLA warning',
  sla_breach: 'SLA breach',
}

/**
 * Shared colour map for the Recharts palette.
 *
 * Categories and priorities keep one colour across badges, charts and legends,
 * which is what makes the analytics page readable at a glance.
 */
export const CHART_COLORS = {
  category: {
    Software: '#4a68f5',
    Hardware: '#0ea5e9',
    Network: '#7c2ce0',
    Login: '#f97316',
    VPN: '#0d9488',
    Access: '#b45309',
  },
  priority: {
    Critical: '#e11d48',
    High: '#f97316',
    Medium: '#eab308',
    Low: '#10b981',
  },
  status: {
    Open: '#4a68f5',
    'In Progress': '#eab308',
    Resolved: '#10b981',
  },
  axis: '#98a2b3',
  grid: '#eaecf0',
}

/** Parse a UTC ISO timestamp into a Date, tolerating a missing value. */
export function parseDate(value) {
  if (!value) return null
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? null : date
}

export function formatDateTime(value) {
  const date = parseDate(value)
  if (!date) return '-'
  return date.toLocaleString(undefined, {
    year: 'numeric',
    month: 'short',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

export function formatDate(value) {
  const date = parseDate(value)
  if (!date) return '-'
  return date.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: '2-digit' })
}

/** "3h 12m" style relative age, used in ticket lists. */
export function formatRelative(value) {
  const date = parseDate(value)
  if (!date) return '-'
  const seconds = Math.round((Date.now() - date.getTime()) / 1000)
  const future = seconds < 0
  const abs = Math.abs(seconds)

  const units = [
    ['year', 31536000],
    ['month', 2592000],
    ['day', 86400],
    ['hour', 3600],
    ['minute', 60],
  ]
  for (const [name, size] of units) {
    if (abs >= size) {
      const n = Math.floor(abs / size)
      return future ? `in ${n} ${name}${n > 1 ? 's' : ''}` : `${n} ${name}${n > 1 ? 's' : ''} ago`
    }
  }
  return future ? 'in a moment' : 'just now'
}

export function formatHours(hours) {
  if (hours === null || hours === undefined || Number.isNaN(Number(hours))) return '-'
  const value = Number(hours)
  if (value < 1) return `${Math.round(value * 60)}m`
  if (value < 24) return `${value.toFixed(1)}h`
  const days = value / 24
  return `${days.toFixed(1)}d (${value.toFixed(1)}h)`
}

export function formatPercent(value, digits = 1) {
  if (value === null || value === undefined) return '-'
  return `${Number(value).toFixed(digits)}%`
}

/**
 * Build the query string for a list endpoint from a filter object, dropping
 * empty values so the backend's own defaults apply.
 */
export function toQuery(params = {}) {
  const query = {}
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === '') continue
    if (Array.isArray(value)) {
      if (!value.length) continue
      query[key] = value.join(',')
    } else {
      query[key] = value
    }
  }
  return query
}

export function initials(name) {
  if (!name) return '?'
  return name
    .split(' ')
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0].toUpperCase())
    .join('')
}