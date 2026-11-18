import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useAsync } from '../hooks/useAsync.js'
import { notificationApi } from '../services/api'
import { useAuth } from '../context/AuthContext.jsx'
import {
  NOTIFICATION_TYPE_LABEL,
  formatRelative,
  notificationTypeClass,
  toQuery,
} from '../utils/format.jsx'
import {
  Alert,
  Card,
  EmptyState,
  ErrorState,
  PageHeader,
  Pagination,
  SkeletonList,
} from '../components/ui.jsx'
import {
  ActivityIcon,
  AlertTriangleIcon,
  BellIcon,
  CheckCircleIcon,
  CheckIcon,
  ClockIcon,
  TicketIcon,
  UsersIcon,
} from '../components/icons.jsx'

/** Where a notification's ticket lives, depending on who is reading it. */
function ticketHref(role, ticketId) {
  if (!ticketId) return null
  if (role === 'admin') return `/admin/tickets/${ticketId}`
  if (role === 'agent') return `/agent/tickets/${ticketId}`
  return `/tickets/${ticketId}`
}

/**
 * Icon and emphasis per notification type.
 *
 * `emphasis` drives the icon tile colour so an SLA breach is impossible to
 * scroll past, while the rest stay visually quiet.
 */
const TYPE_PRESENTATION = {
  ticket_created: { Icon: TicketIcon, emphasis: 'brand' },
  ticket_assigned: { Icon: UsersIcon, emphasis: 'sky' },
  ticket_status: { Icon: ActivityIcon, emphasis: 'amber' },
  ticket_resolved: { Icon: CheckCircleIcon, emphasis: 'emerald' },
  sla_warning: { Icon: ClockIcon, emphasis: 'orange' },
  sla_breach: { Icon: AlertTriangleIcon, emphasis: 'rose' },
}

const TILE_TONES = {
  brand: 'bg-brand-50 text-brand-600',
  sky: 'bg-sky-50 text-sky-600',
  amber: 'bg-amber-50 text-amber-600',
  orange: 'bg-orange-50 text-orange-600',
  emerald: 'bg-emerald-50 text-emerald-600',
  rose: 'bg-rose-50 text-rose-600',
}

export default function Notifications() {
  const { role } = useAuth()
  const [page, setPage] = useState(1)
  const [unreadOnly, setUnreadOnly] = useState(false)
  const [busyId, setBusyId] = useState(null)
  const [markingAll, setMarkingAll] = useState(false)
  const [notice, setNotice] = useState(null)
  const [noticeTone, setNoticeTone] = useState('info')

  const { data, loading, error, reload } = useAsync(
    () => notificationApi.list(toQuery({ page, page_size: 15, unread_only: unreadOnly ? '1' : '' })),
    [page, unreadOnly],
  )

  const notifications = data?.items ?? []
  const unreadCount = data?.unread_count ?? 0

  async function markOne(id) {
    setBusyId(id)
    try {
      await notificationApi.markRead(id)
      await reload()
    } catch (err) {
      setNoticeTone('danger')
      setNotice(err.message)
    } finally {
      setBusyId(null)
    }
  }

  async function markAll() {
    setMarkingAll(true)
    try {
      const result = await notificationApi.markAllRead()
      setNoticeTone('success')
      setNotice(result.message ?? 'All notifications marked as read.')
      await reload()
    } catch (err) {
      setNoticeTone('danger')
      setNotice(err.message)
    } finally {
      setMarkingAll(false)
    }
  }

  function toggleUnread() {
    setUnreadOnly((current) => !current)
    setPage(1)
  }

  return (
    <>
      <PageHeader
        eyebrow="Your account"
        title="Notifications"
        description="Assignments, status changes and SLA warnings raised for your account."
        actions={
          <>
            <button
              type="button"
              onClick={toggleUnread}
              className={unreadOnly ? 'btn-primary' : 'btn-secondary'}
              aria-pressed={unreadOnly}
            >
              <CheckIcon className="h-4 w-4" />
              {unreadOnly ? 'Showing unread' : 'Show unread only'}
            </button>
            <button
              type="button"
              className="btn-secondary"
              onClick={markAll}
              disabled={!unreadCount || markingAll}
            >
              {markingAll ? 'Marking…' : 'Mark all read'}
            </button>
          </>
        }
      />

      {notice && (
        <div className="mb-5">
          <Alert tone={noticeTone} onDismiss={() => setNotice(null)}>
            {notice}
          </Alert>
        </div>
      )}

      {unreadCount > 0 && (
        <div className="mb-5 flex items-center gap-3 rounded-2xl border border-brand-200 bg-brand-50/70 px-4 py-3">
          <span className="relative inline-flex h-2.5 w-2.5 shrink-0">
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-brand-400 opacity-75" />
            <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-brand-600" />
          </span>
          <p className="text-sm font-medium text-brand-900">
            {unreadCount} unread notification{unreadCount === 1 ? '' : 's'}
          </p>
        </div>
      )}

      {loading && <SkeletonList rows={6} />}
      {error && <ErrorState error={error} onRetry={reload} />}

      {!loading && !error && notifications.length === 0 && (
        <EmptyState
          icon={BellIcon}
          title={unreadOnly ? 'Nothing unread' : 'No notifications yet'}
          description={
            unreadOnly
              ? 'You have read everything. Switch the filter off to see older notifications.'
              : 'Updates about your tickets will appear here.'
          }
          action={
            unreadOnly ? (
              <button type="button" className="btn-secondary" onClick={toggleUnread}>
                Show all notifications
              </button>
            ) : null
          }
        />
      )}

      {!loading && !error && notifications.length > 0 && (
        <Card bodyClass="p-0">
          <ul className="divide-y divide-hairline">
            {notifications.map((item) => {
              const href = ticketHref(role, item.ticket_id)
              const { Icon, emphasis } = TYPE_PRESENTATION[item.type] ?? {
                Icon: BellIcon,
                emphasis: 'brand',
              }

              return (
                <li
                  key={item.id}
                  className={`flex gap-4 px-4 py-4 transition sm:px-5 ${
                    item.is_read ? 'bg-white' : 'bg-brand-50/40'
                  }`}
                >
                  <span
                    className={`inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-xl ${
                      TILE_TONES[emphasis]
                    }`}
                  >
                    <Icon className="h-4 w-4" />
                  </span>

                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                      <p
                        className={`text-sm leading-snug ${
                          item.is_read ? 'font-semibold text-ink' : 'font-bold text-ink'
                        }`}
                      >
                        {item.title}
                      </p>
                      <span className={`badge ${notificationTypeClass[item.type] ?? ''}`}>
                        {NOTIFICATION_TYPE_LABEL[item.type] ?? item.type}
                      </span>
                      {!item.is_read && (
                        <span className="badge badge-soft bg-brand-100 text-brand-700">New</span>
                      )}
                    </div>

                    <p className="mt-1 text-sm leading-relaxed text-ink-soft">{item.message}</p>

                    <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1.5">
                      <span className="text-xs text-ink-faint">
                        {formatRelative(item.created_at)}
                      </span>
                      {href && (
                        <Link
                          to={href}
                          className="text-xs font-semibold text-brand-700 hover:underline"
                        >
                          View ticket
                        </Link>
                      )}
                      {!item.is_read && (
                        <button
                          type="button"
                          className="text-xs font-semibold text-ink-muted hover:text-ink hover:underline"
                          onClick={() => markOne(item.id)}
                          disabled={busyId === item.id}
                        >
                          {busyId === item.id ? 'Marking…' : 'Mark as read'}
                        </button>
                      )}
                    </div>
                  </div>
                </li>
              )
            })}
          </ul>
          <Pagination pagination={data?.pagination} onChange={setPage} />
        </Card>
      )}
    </>
  )
}