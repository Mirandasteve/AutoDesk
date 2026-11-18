import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAsync, useDebounced } from '../../hooks/useAsync.js'
import { agentApi } from '../../services/api'
import { useAuth } from '../../context/AuthContext.jsx'
import {
  CategoryBadge,
  PriorityBadge,
  SlaBadge,
  StatusBadge,
  formatRelative,
  toQuery,
} from '../../utils/format.jsx'
import {
  Card,
  DataTable,
  EmptyState,
  ErrorState,
  PageHeader,
  Pagination,
  SkeletonStats,
  SkeletonTable,
  StatCard,
} from '../../components/ui.jsx'
import TicketFilters from '../../components/TicketFilters.jsx'
import {
  ArrowRightIcon,
  CheckCircleIcon,
  ClockIcon,
  InboxIcon,
  LayersIcon,
} from '../../components/icons.jsx'

const COLUMNS = [
  {
    key: 'id',
    header: 'Ticket',
    render: (t) => (
      <span className="whitespace-nowrap text-xs font-semibold tabular-nums text-ink-faint">
        #{t.id}
      </span>
    ),
  },
  {
    key: 'title',
    header: 'Summary',
    render: (t) => (
      <div className="min-w-0">
        <p className="truncate font-semibold text-ink">{t.title}</p>
        <p className="truncate text-xs text-ink-muted">
          {t.creator?.name ?? 'Unknown employee'}
          {t.confidence != null && ` · ${Math.round(t.confidence * 100)}% confident`}
        </p>
      </div>
    ),
  },
  { key: 'category', header: 'Category', render: (t) => <CategoryBadge value={t.category} /> },
  { key: 'priority', header: 'Priority', render: (t) => <PriorityBadge value={t.priority} /> },
  { key: 'status', header: 'Status', render: (t) => <StatusBadge value={t.status} /> },
  { key: 'assignee', header: 'Assigned', render: (t) => t.assignee?.name ?? '—' },
  { key: 'sla', header: 'SLA', render: (t) => <SlaBadge ticket={t} /> },
  {
    key: 'created_at',
    header: 'Raised',
    cellClassName: 'whitespace-nowrap text-ink-muted',
    render: (t) => formatRelative(t.created_at),
  },
]

const EMPTY_FILTERS = { status: '', priority: '', category: '', assigned: '', search: '' }

/**
 * The team queue.
 *
 * The backend pins an agent to their own team (`user.team`, or the empty
 * `"__no_team__"` scope when unassigned) and defaults the sort to
 * `priority desc`, so Critical rows appear first without any client ordering.
 */
export default function AgentQueue() {
  const navigate = useNavigate()
  const { user } = useAuth()
  const [filters, setFilters] = useState(EMPTY_FILTERS)
  const [page, setPage] = useState(1)
  const debouncedSearch = useDebounced(filters.search, 400)

  const { data, loading, error, reload } = useAsync(
    () =>
      agentApi.tickets(
        toQuery({
          status: filters.status,
          priority: filters.priority,
          category: filters.category,
          search: debouncedSearch,
          assigned_to: filters.assigned,
          page,
          page_size: 15,
        }),
      ),
    [filters.status, filters.priority, filters.category, debouncedSearch, filters.assigned, page],
  )

  function update(key, value) {
    setFilters((current) => ({ ...current, [key]: value }))
    setPage(1)
  }

  function reset() {
    setFilters(EMPTY_FILTERS)
    setPage(1)
  }

  const tickets = data?.items ?? []
  const counts = data?.counts ?? {}

  return (
    <>
      <PageHeader
        eyebrow="Support desk"
        title="Team queue"
        description={`Tickets routed to ${user?.team ?? 'your team'}. Critical and High work appears first.`}
        actions={
          <Link to="/agent/my-tickets" className="btn-secondary">
            My assignments
            <ArrowRightIcon className="h-4 w-4" />
          </Link>
        }
      />

      {counts.by_status && (
        <div className="mb-6 grid gap-4 sm:grid-cols-3">
          <StatCard
            label="Open"
            value={counts.by_status.Open ?? 0}
            tone="brand"
            icon={InboxIcon}
          />
          <StatCard
            label="In Progress"
            value={counts.by_status['In Progress'] ?? 0}
            tone="warning"
            icon={ClockIcon}
          />
          <StatCard
            label="Resolved"
            value={counts.by_status.Resolved ?? 0}
            tone="success"
            icon={CheckCircleIcon}
          />
        </div>
      )}

      <TicketFilters
        value={filters}
        onChange={update}
        onReset={reset}
        fields={['status', 'priority', 'category', 'assigned']}
      />

      {loading && (
        <>
          <SkeletonStats count={3} />
          <div className="card mt-6">
            <SkeletonTable rows={7} cols={6} />
          </div>
        </>
      )}
      {error && <ErrorState error={error} onRetry={reload} />}

      {!loading && !error && (
        <Card bodyClass="p-0">
          <DataTable
            columns={COLUMNS}
            rows={tickets}
            empty={
              <EmptyState
                icon={LayersIcon}
                title="No tickets in this queue"
                description="Adjust the filters, or check back once new tickets are routed to your team."
              />
            }
            onRowClick={(t) => navigate(`/agent/tickets/${t.id}`)}
          />
          <Pagination pagination={data?.pagination} onChange={setPage} />
        </Card>
      )}
    </>
  )
}
