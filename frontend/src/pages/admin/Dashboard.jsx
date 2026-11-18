import { Link, useNavigate } from 'react-router-dom'
import { useAsync } from '../../hooks/useAsync.js'
import { adminApi } from '../../services/api'
import {
  CategoryBadge,
  PriorityBadge,
  SlaBadge,
  StatusBadge,
  formatHours,
  formatPercent,
  formatRelative,
  initials,
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
  ActivityIcon,
  AlertTriangleIcon,
  ArrowRightIcon,
  AwardIcon,
  CheckCircleIcon,
  ClockIcon,
  CpuIcon,
  InboxIcon,
  LayersIcon,
  TargetIcon,
  TicketIcon,
  UsersIcon,
} from '../../components/icons.jsx'

const RECENT_COLUMNS = [
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
    key: 'created_at',
    header: 'Raised',
    cellClassName: 'whitespace-nowrap text-ink-muted',
    render: (t) => formatRelative(t.created_at),
  },
]

/**
 * Administrator landing page.
 *
 * Mirrors the SRS section 48 layout: total / open / in progress / resolved on
 * the first row, then critical, high, average resolution time and SLA
 * compliance. All figures come from live SQL aggregates.
 */
export default function AdminDashboard() {
  const navigate = useNavigate()
  const { data, loading, error, reload } = useAsync(() => adminApi.dashboard(), [])

  if (loading) {
    return (
      <>
        <SkeletonStats />
        <div className="mt-4">
          <SkeletonStats />
        </div>
        <div className="card mt-6">
          <SkeletonTable rows={6} cols={6} />
        </div>
      </>
    )
  }
  if (error) return <ErrorState error={error} onRetry={reload} />

  const summary = data?.summary ?? {}
  const sla = data?.sla ?? {}
  const teams = data?.teams ?? []
  const agents = data?.top_agents ?? []
  const recent = data?.recent_tickets ?? []
  const users = data?.users ?? {}

  return (
    <>
      <PageHeader
        eyebrow="Administration"
        title="System overview"
        description="Ticket volume, SLA health and team performance across the whole platform."
        actions={
          <>
            <Link to="/admin/analytics" className="btn-secondary">
              Analytics
            </Link>
            <Link to="/admin/ml" className="btn-secondary">
              <CpuIcon className="h-4 w-4" />
              ML status
            </Link>
          </>
        }
      />

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          label="Total tickets"
          value={summary.total_tickets ?? 0}
          tone="brand"
          icon={TicketIcon}
        />
        <StatCard
          label="Open"
          value={summary.open_tickets ?? 0}
          hint="Awaiting first response"
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
          label="Resolved"
          value={summary.resolved_tickets ?? 0}
          tone="success"
          hint={`Avg ${summary.avg_resolution_time_display ?? '—'}`}
          icon={CheckCircleIcon}
        />
      </div>

      <div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          label="Critical"
          value={summary.critical_tickets ?? 0}
          tone="danger"
          hint="2h SLA window"
          icon={AlertTriangleIcon}
        />
        <StatCard
          label="High"
          value={summary.high_tickets ?? 0}
          tone="warning"
          hint="4h SLA window"
          icon={ActivityIcon}
        />
        <StatCard
          label="SLA compliance"
          value={formatPercent(sla.sla_compliance_rate)}
          tone="success"
          hint={`${sla.total_breached ?? 0} breached of ${sla.total ?? 0}`}
          icon={TargetIcon}
        />
        <StatCard
          label="Users"
          value={users.total ?? '—'}
          hint={`${users.employee ?? 0} employees · ${users.agent ?? 0} agents · ${users.admin ?? 0} admins`}
          icon={UsersIcon}
        />
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-3">
        <Card
          className="lg:col-span-2"
          title="Recent tickets"
          subtitle="Newest activity across every team"
          icon={TicketIcon}
          bodyClass="p-0"
          actions={
            <Link to="/admin/tickets" className="btn-secondary btn-sm">
              All tickets
              <ArrowRightIcon className="h-3.5 w-3.5" />
            </Link>
          }
        >
          <DataTable
            columns={RECENT_COLUMNS}
            rows={recent}
            empty={
              <EmptyState
                icon={TicketIcon}
                title="No tickets yet"
                description="Raise one from the employee portal to see it appear here."
              />
            }
            onRowClick={(t) => navigate(`/admin/tickets/${t.id}`)}
          />
        </Card>

        <div className="space-y-6">
          <Card
            title="Team performance"
            subtitle="From the live routing table"
            icon={LayersIcon}
          >
            {teams.length === 0 ? (
              <p className="text-sm text-ink-muted">No teams configured.</p>
            ) : (
              <ul className="space-y-2.5">
                {teams.map((team) => (
                  <li
                    key={team.team}
                    className="rounded-xl border border-hairline p-3.5 transition hover:border-brand-200 hover:bg-brand-50/30"
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="flex min-w-0 items-center gap-2.5">
                        <span className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-brand-50 text-xs font-bold text-brand-700 ring-1 ring-brand-100">
                          {initials(team.team)}
                        </span>
                        <div className="min-w-0">
                          <p className="truncate text-[0.8125rem] font-semibold text-ink">
                            {team.team}
                          </p>
                          <p className="truncate text-xs text-ink-muted">
                            {team.handles_categories?.join(', ')}
                          </p>
                        </div>
                      </div>
                      <span className="chip shrink-0">
                        {team.agents} agent{team.agents === 1 ? '' : 's'}
                      </span>
                    </div>
                    <div className="mt-2.5 flex flex-wrap gap-1.5">
                      <span className="badge badge-soft badge-open">{team.open} open</span>
                      <span className="badge badge-soft badge-in-progress">
                        {team.in_progress} active
                      </span>
                      <span className="badge badge-soft badge-resolved">
                        {team.resolved} resolved
                      </span>
                      {team.urgent > 0 && (
                        <span className="badge badge-soft badge-critical">{team.urgent} urgent</span>
                      )}
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </Card>

          <Card title="Top agents" subtitle="Ranked by resolved tickets" icon={AwardIcon}>
            {agents.length === 0 ? (
              <p className="text-sm text-ink-muted">No resolutions recorded yet.</p>
            ) : (
              <ol className="space-y-2">
                {agents.map((agent, index) => (
                  <li
                    key={agent.user_id}
                    className="flex items-center gap-3 rounded-xl px-2 py-2 odd:bg-slate-50/70"
                  >
                    <span
                      className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-xs font-bold ${
                        index === 0
                          ? 'bg-amber-100 text-amber-700'
                          : index === 1
                            ? 'bg-slate-200 text-slate-600'
                            : 'bg-slate-100 text-slate-500'
                      }`}
                    >
                      {index + 1}
                    </span>
                    <span className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-brand-100 text-[0.625rem] font-bold text-brand-700">
                      {initials(agent.name)}
                    </span>
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-[0.8125rem] font-semibold text-ink">
                        {agent.name}
                      </p>
                      <p className="truncate text-xs text-ink-muted">
                        {agent.team ?? 'Unassigned team'}
                      </p>
                    </div>
                    <div className="shrink-0 text-right">
                      <p className="text-[0.8125rem] font-bold tabular-nums text-ink">
                        {agent.resolved_tickets}
                      </p>
                      <p className="text-xs tabular-nums text-ink-muted">
                        {agent.avg_resolution_hours != null
                          ? formatHours(agent.avg_resolution_hours)
                          : '—'}
                      </p>
                    </div>
                  </li>
                ))}
              </ol>
            )}
          </Card>
        </div>
      </div>
    </>
  )
}
