import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../../context/AuthContext.jsx'
import { useMeta } from '../../context/MetaContext.jsx'
import { ticketApi } from '../../services/api'
import { useAsync } from '../../hooks/useAsync.js'
import {
  CategoryBadge,
  PriorityBadge,
  SlaBadge,
  StatusBadge,
  formatRelative,
} from '../../utils/format.jsx'
import {
  Card,
  DataTable,
  EmptyState,
  ErrorState,
  PageHeader,
  SkeletonStats,
  SkeletonTable,
  StatCard,
} from '../../components/ui.jsx'
import {
  ArrowRightIcon,
  CheckCircleIcon,
  ClockIcon,
  CpuIcon,
  InboxIcon,
  LayersIcon,
  ListChecksIcon,
  PlusIcon,
  TicketIcon,
  TargetIcon,
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
        <p className="truncate text-xs text-ink-muted">{t.assigned_team}</p>
      </div>
    ),
  },
  {
    key: 'category',
    header: 'Category',
    render: (t) => <CategoryBadge value={t.category} />,
  },
  {
    key: 'priority',
    header: 'Priority',
    render: (t) => <PriorityBadge value={t.priority} />,
  },
  {
    key: 'status',
    header: 'Status',
    render: (t) => <StatusBadge value={t.status} />,
  },
  {
    key: 'sla',
    header: 'SLA',
    render: (t) => <SlaBadge ticket={t} />,
  },
  {
    key: 'created_at',
    header: 'Raised',
    cellClassName: 'whitespace-nowrap text-ink-muted',
    render: (t) => formatRelative(t.created_at),
  },
]

/** The three-stage pipeline, explained once and reused in two places. */
const PIPELINE_STEPS = [
  {
    icon: CpuIcon,
    title: 'DistilBERT classifies',
    body: 'Your title and description are classified into one of six categories with a confidence score.',
  },
  {
    icon: TargetIcon,
    title: 'Priority engine scores',
    body: 'Rule-based scoring assigns Critical, High, Medium or Low and records the reason.',
  },
  {
    icon: LayersIcon,
    title: 'Routing engine assigns',
    body: 'The category maps to a support team and an SLA deadline is set.',
  },
]

/**
 * Employee landing page.
 *
 * Everything here comes from `GET /api/tickets` (already scoped to the caller
 * server-side) plus the public `GET /api/auth/stats` counters. The status
 * tiles are counted from the loaded page rather than from a separate endpoint,
 * because a second endpoint could disagree with the list the user is looking
 * at.
 */
export default function EmployeeDashboard() {
  const { user } = useAuth()
  const navigate = useNavigate()
  const { data, loading, error, reload } = useAsync(() => ticketApi.mine({ page_size: 50 }), [])
  const { slaHours } = useMeta()

  const tickets = data?.items ?? []
  const total = data?.pagination?.total ?? tickets.length

  const counts = tickets.reduce(
    (acc, t) => {
      acc[t.status] = (acc[t.status] ?? 0) + 1
      return acc
    },
    { Open: 0, 'In Progress': 0, Resolved: 0 },
  )

  const firstName = user?.name?.split(' ')[0] ?? 'there'

  return (
    <>
      <PageHeader
        eyebrow="Employee portal"
        title={`Welcome back, ${firstName}`}
        description="Track your support requests, or raise a new one and let the model route it."
        actions={
          <Link to="/tickets/new" className="btn-primary">
            <PlusIcon className="h-4 w-4" />
            Raise a Ticket
          </Link>
        }
      />

      {loading && (
        <>
          <SkeletonStats />
          <div className="card mt-6">
            <SkeletonTable rows={5} cols={5} />
          </div>
        </>
      )}
      {error && <ErrorState error={error} onRetry={reload} />}

      {!loading && !error && (
        <>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <StatCard
              label="Total tickets"
              value={total}
              hint="Raised by you"
              icon={TicketIcon}
            />
            <StatCard
              label="Open"
              value={counts.Open}
              tone="brand"
              hint="Waiting for an agent"
              icon={InboxIcon}
            />
            <StatCard
              label="In Progress"
              value={counts['In Progress']}
              tone="warning"
              hint="Being worked on"
              icon={ClockIcon}
            />
            <StatCard
              label="Resolved"
              value={counts.Resolved}
              tone="success"
              hint="Closed by support"
              icon={CheckCircleIcon}
            />
          </div>

          <div className="mt-6 grid gap-6 lg:grid-cols-3">
            <Card
              className="lg:col-span-2"
              title="Recent tickets"
              subtitle="Newest first"
              icon={TicketIcon}
              bodyClass="p-0"
              actions={
                <Link to="/tickets/my" className="btn-secondary btn-sm">
                  View all
                  <ArrowRightIcon className="h-3.5 w-3.5" />
                </Link>
              }
            >
              <DataTable
                columns={COLUMNS}
                rows={tickets.slice(0, 8)}
                empty={
                  <EmptyState
                    icon={TicketIcon}
                    title="No tickets yet"
                    description="When you raise a ticket, DistilBERT classifies it and the routing engine assigns the team automatically."
                    action={
                      <Link to="/tickets/new" className="btn-primary">
                        <PlusIcon className="h-4 w-4" />
                        Raise your first ticket
                      </Link>
                    }
                  />
                }
                onRowClick={(t) => navigate(`/tickets/${t.id}`)}
              />
            </Card>

            <div className="space-y-6">
              <Card title="How classification works" icon={ListChecksIcon}>
                <ol className="space-y-4">
                  {PIPELINE_STEPS.map((step, index) => {
                    const StepIcon = step.icon
                    return (
                      <li key={step.title} className="flex gap-3.5">
                        <span className="relative flex flex-col items-center">
                          <span className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-brand-50 text-brand-600 ring-1 ring-brand-100">
                            <StepIcon className="h-[18px] w-[18px]" />
                          </span>
                          {index < PIPELINE_STEPS.length - 1 && (
                            <span
                              aria-hidden="true"
                              className="mt-1 h-4 w-px bg-slate-200"
                            />
                          )}
                        </span>
                        <div className="min-w-0 pt-0.5">
                          <p className="text-[0.8125rem] font-semibold text-ink">
                            {index + 1}. {step.title}
                          </p>
                          <p className="mt-0.5 text-[0.8125rem] leading-relaxed text-ink-muted">
                            {step.body}
                          </p>
                        </div>
                      </li>
                    )
                  })}
                </ol>
              </Card>

              {Object.keys(slaHours).length > 0 && (
                <Card title="SLA targets" subtitle="Set automatically from the priority" icon={TargetIcon}>
                  <dl className="space-y-1">
                    {Object.entries(slaHours).map(([priority, hours]) => (
                      <div
                        key={priority}
                        className="flex items-center justify-between rounded-lg px-2 py-1.5 odd:bg-slate-50/70"
                      >
                        <dt>
                          <PriorityBadge value={priority} />
                        </dt>
                        <dd className="font-semibold tabular-nums text-ink">{hours}h</dd>
                      </div>
                    ))}
                  </dl>
                </Card>
              )}
            </div>
          </div>
        </>
      )}
    </>
  )
}
