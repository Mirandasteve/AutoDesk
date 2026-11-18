import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAsync, useDebounced } from '../../hooks/useAsync.js'
import { ticketApi } from '../../services/api'
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
import { PlusIcon, TicketIcon } from '../../components/icons.jsx'

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
          {t.assigned_team}
          {t.assignee ? ` · ${t.assignee.name}` : ' · unassigned'}
        </p>
      </div>
    ),
  },
  { key: 'category', header: 'Category', render: (t) => <CategoryBadge value={t.category} /> },
  { key: 'priority', header: 'Priority', render: (t) => <PriorityBadge value={t.priority} /> },
  { key: 'status', header: 'Status', render: (t) => <StatusBadge value={t.status} /> },
  { key: 'sla', header: 'SLA', render: (t) => <SlaBadge ticket={t} /> },
  {
    key: 'created_at',
    header: 'Raised',
    cellClassName: 'whitespace-nowrap text-ink-muted',
    render: (t) => formatRelative(t.created_at),
  },
]

const EMPTY_FILTERS = { status: '', priority: '', category: '', search: '' }

/**
 * All tickets raised by the signed-in employee, with filters and pagination.
 *
 * The backend scopes this to `created_by = me`, so there is no client-side
 * ownership check to get wrong.
 */
export default function MyTickets() {
  const navigate = useNavigate()
  const [filters, setFilters] = useState(EMPTY_FILTERS)
  const [page, setPage] = useState(1)
  const debouncedSearch = useDebounced(filters.search, 400)

  const { data, loading, error, reload } = useAsync(
    () => ticketApi.mine(toQuery({ ...filters, search: debouncedSearch, page, page_size: 15 })),
    [filters.status, filters.priority, filters.category, debouncedSearch, page],
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
        eyebrow="Employee portal"
        title="My tickets"
        description="Every ticket you have raised, with the classification the model assigned."
        actions={
          <Link to="/tickets/new" className="btn-primary">
            <PlusIcon className="h-4 w-4" />
            Raise a ticket
          </Link>
        }
      />

      <TicketFilters
        value={filters}
        onChange={update}
        onReset={reset}
        fields={['status', 'priority', 'category']}
      />

      {loading && (
        <div className="card">
          <SkeletonTable rows={7} cols={6} />
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
                icon={TicketIcon}
                title="No tickets match"
                description="Try clearing the filters, or raise a new ticket."
                action={
                  <Link to="/tickets/new" className="btn-primary">
                    <PlusIcon className="h-4 w-4" />
                    Raise a ticket
                  </Link>
                }
              />
            }
            onRowClick={(t) => navigate(`/tickets/${t.id}`)}
          />
          <Pagination pagination={data?.pagination} onChange={setPage} />
        </Card>
      )}
    </>
  )
}
