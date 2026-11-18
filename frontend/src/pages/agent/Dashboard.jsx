import { Link, useNavigate } from 'react-router-dom'
import { useAsync } from '../../hooks/useAsync.js'
import { agentApi } from '../../services/api'
import { useAuth } from '../../context/AuthContext.jsx'
import {
  CategoryBadge,
  PriorityBadge,
  SlaBadge,
  StatusBadge,
  formatHours,
  formatPercent,
  formatRelative,
} from '../../utils/format.jsx'
import {
  Card,
  DataTable,
  EmptyState,
  ErrorState,
  KeyValue,
  PageHeader,
  SkeletonStats,
  SkeletonTable,
  StatCard,
} from '../../components/ui.jsx'
import {
  AlertTriangleIcon,
  ArrowRightIcon,
  AwardIcon,
  CheckCircleIcon,
  ClockIcon,
  HandIcon,
  InboxIcon,
  TargetIcon,
  TicketIcon,
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
          {t.assignee?.name ?? 'Unassigned'} · {t.creator?.name ?? 'Unknown'}
        </p>
      </div>
    ),
  },
  { key: 'category', header: 'Category', render: (t) => <CategoryBadge value={t.category} /> },
  { key: 'priority', header: 'Priority', render: (t) => <PriorityBadge value={t.priority} /> },
  { key: 'status', header: 'Status', render: (t) => <StatusBadge value={t.status} /> },
  { key: 'sla', header: 'SLA', render: (t) => <SlaBadge ticket={t} /> },
]

/**
 * Agent landing page.
 *
 * `GET /api/agent/dashboard` returns the counters, the SLA snapshot, the
 * Critical/High alerts and the first page of the team queue in one request, so
 * this screen needs exactly one round trip.
 */
export default function AgentDashboard() {
  const { user } = useAuth()
  const navigate = useNavigate()
  const { data, loading, error, reload } = useAsync(() => agentApi.dashboard(), [])

  if (loading) {
    return (
      <>
        <SkeletonStats />
        <div className="mt-6 grid gap-6 lg:grid-cols-3">
          <div className="card lg:col-span-2">
            <SkeletonTable rows={6} cols={5} />
          </div>
          <div className="card space-y-4 p-6">
            <div className="skeleton h-4 w-32" />
            <div className="skeleton h-16 w-full" />
            <div className="skeleton h-16 w-full" />
          </div>
        </div>
      </>
    )
  }
  if (error) return <ErrorState error={error} onRetry={reload} />

  const summary = data?.summary ?? {}
  const sla = data?.sla ?? {}
  const alerts = data?.critical_alerts ?? []
  const queue = data?.queue ?? []
  const compliance = Number(sla.sla_compliance_rate ?? 0)

  return (
    <>
      <PageHeader
        eyebrow="Support desk"
        title={`${user?.team ?? 'Support'} dashboard`}
        description={data?.team_description || 'Tickets routed to your support team, most urgent first.'}
        actions={
          <>
            <Link to="/agent/tickets" className="btn-secondary">
              Open queue
            </Link>
            <Link to="/agent/my-tickets" className="btn-primary">
              <HandIcon className="h-4 w-4" />
              My assignments
            </Link>
          </>
        }
      />

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          label="Assigned to me"
          value={summary.assigned_to_me ?? 0}
          tone="brand"
          hint={`${summary.unresolved_tickets ?? 0} unresolved in team`}
          icon={HandIcon}
        />
        <StatCard
          label="Open"
          value={summary.open_tickets ?? 0}
          hint="Waiting to be picked up"
          icon={InboxIcon}
        />
        <StatCard
          label="In Progress"
          value={summary.in_progress_tickets ?? 0}
          tone="warning"
          hint="Being worked on"
          icon={ClockIcon}
        />
        <StatCard
          label="Avg resolution"
          value={summary.avg_resolution_time_display ?? '—'}
          tone="success"
          hint={`${summary.resolved_tickets ?? 0} resolved`}
          icon={AwardIcon}
        />
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-3">
        <Card
          className="lg:col-span-2"
          title="Queue"
          subtitle="Most urgent first"
          icon={TicketIcon}
          bodyClass="p-0"
          actions={<span className="chip">{data?.queue_total ?? queue.length} total</span>}
        >
          <DataTable
            columns={COLUMNS}
            rows={queue}
            empty={
              <EmptyState
                icon={CheckCircleIcon}
                title="Queue is clear"
                description="No tickets are currently routed to your team."
              />
            }
            onRowClick={(t) => navigate(`/agent/tickets/${t.id}`)}
          />
        </Card>

        <div className="space-y-6">
          <Card
            title="Critical & High"
            subtitle="Open tickets needing attention"
            icon={AlertTriangleIcon}
            actions={<span className="badge badge-soft badge-critical">{alerts.length}</span>}
          >
            {alerts.length === 0 ? (
              <EmptyState
                icon={CheckCircleIcon}
                title="Nothing urgent"
                description="No open Critical or High tickets are waiting."
              />
            ) : (
              <ul className="space-y-2.5">
                {alerts.map((t) => (
                  <li key={t.id}>
                    <Link
                      to={`/agent/tickets/${t.id}`}
                      className="card-interactive block rounded-xl border border-hairline p-3.5"
                    >
                      <div className="flex items-start justify-between gap-2">
                        <PriorityBadge value={t.priority} />
                        <span className="shrink-0 text-xs text-ink-faint">
                          {formatRelative(t.created_at)}
                        </span>
                      </div>
                      <p className="mt-2 text-[0.8125rem] font-semibold leading-snug text-ink">
                        {t.title}
                      </p>
                      <div className="mt-2 flex flex-wrap items-center gap-1.5">
                        <SlaBadge ticket={t} />
                        <CategoryBadge value={t.category} />
                      </div>
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </Card>

          <Card
            title="SLA snapshot"
            subtitle="Across the whole team queue"
            icon={TargetIcon}
          >
            <div
              className={`rounded-xl p-4 ${
                compliance >= 95
                  ? 'bg-emerald-50 ring-1 ring-emerald-100'
                  : compliance >= 85
                    ? 'bg-amber-50 ring-1 ring-amber-100'
                    : 'bg-rose-50 ring-1 ring-rose-100'
              }`}
            >
              <p className="micro-label">SLA compliance</p>
              <p className="mt-1 text-3xl font-semibold tracking-tight tabular-nums text-ink">
                {formatPercent(sla.sla_compliance_rate)}
              </p>
              <div className="mt-2.5 h-2 w-full overflow-hidden rounded-full bg-white/70">
                <div
                  className={`h-full rounded-full ${
                    compliance >= 95
                      ? 'bg-emerald-500'
                      : compliance >= 85
                        ? 'bg-amber-500'
                        : 'bg-rose-500'
                  }`}
                  style={{ width: `${Math.max(2, Math.min(100, compliance))}%` }}
                />
              </div>
            </div>

            <dl className="mt-2 divide-y divide-slate-100">
              <KeyValue label="Breached (open)">
                <span className="text-rose-600">{sla.open_breached ?? 0}</span>
              </KeyValue>
              <KeyValue label="Near breach">
                <span className="text-amber-600">{sla.near_sla ?? 0}</span>
              </KeyValue>
              <KeyValue label="Resolved late">{sla.resolved_late ?? 0}</KeyValue>
              {sla.avg_resolution_hours != null && (
                <KeyValue label="Avg resolution">
                  {formatHours(sla.avg_resolution_hours)}
                </KeyValue>
              )}
            </dl>

            <Link
              to="/agent/tickets"
              className="mt-3 inline-flex items-center gap-1.5 text-xs font-semibold text-brand-700 hover:underline"
            >
              Open the full queue
              <ArrowRightIcon className="h-3.5 w-3.5" />
            </Link>
          </Card>
        </div>
      </div>
    </>
  )
}
