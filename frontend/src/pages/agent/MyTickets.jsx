import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAsync, useDebounced } from '../../hooks/useAsync.js'
import { agentApi } from '../../services/api'
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
  SkeletonTable,
} from '../../components/ui.jsx'
import TicketFilters from '../../components/TicketFilters.jsx'
import { ArrowRightIcon, HandIcon } from '../../components/icons.jsx'

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
          {t.creator?.name ?? 'Unknown'} · {t.assigned_team}
        </p>
      </div>
    ),
  },
  { key: 'category', header: 'Category', render: (t) => <CategoryBadge value={t.category} /> },
  { key: 'priority', header: 'Priority', render: (t) => <PriorityBadge value={t.priority} /> },
  { key: 'status', header: 'Status', render: (t) => <StatusBadge value={t.status} /> },
  { key: 'sla', header: 'SLA', render: (t) => <SlaBadge ticket={t} /> },
  {
    key: 'updated_at',
    header: 'Updated',
    cellClassName: 'whitespace-nowrap text-ink-muted',
    render: (t) => formatRelative(t.updated_at),
  },
]

const EMPTY_FILTERS = { status: '', priority: '', search: '' }

/** Tickets explicitly assigned to the acting agent, regardless of team scope. */
export default function AgentMyTickets() {
  const navigate = useNavigate()
  const [filters, setFilters] = useState(EMPTY_FILTERS)
  const [page, setPage] = useState(1)
  const debouncedSearch = useDebounced(filters.search, 400)

  const { data, loading, error, reload } = useAsync(
    () => agentApi.mine(toQuery({ ...filters, search: debouncedSearch, page, page_size: 15 })),
    [filters.status, filters.priority, debouncedSearch, page],
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

  return (
    <>
      <PageHeader
        eyebrow="Support desk"
        title="My assignments"
        description="Tickets you have claimed from the queue."
        actions={
          <Link to="/agent/tickets" className="btn-secondary">
            Team queue
            <ArrowRightIcon className="h-4 w-4" />
          </Link>
        }
      />

      <TicketFilters
        value={filters}
        onChange={update}
        onReset={reset}
        fields={['status', 'priority']}
      />

      {loading && (
        <div className="card">
          <SkeletonTable rows={6} cols={5} />
        </div>
      )}
      {error && <ErrorState error={error} onRetry={reload} />}

      {!loading && !error && (
        <Card bodyClass="p-0">
          <DataTable
            columns={COLUMNS}
            rows={tickets}
            empty={
              <EmptyState
                icon={HandIcon}
                title="Nothing assigned to you"
                description="Claim a ticket from the team queue to start working on it."
                action={
                  <Link to="/agent/tickets" className="btn-primary">
                    Browse the queue
                    <ArrowRightIcon className="h-4 w-4" />
                  </Link>
                }
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
