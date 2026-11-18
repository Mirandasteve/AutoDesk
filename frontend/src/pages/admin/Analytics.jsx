import { Link } from 'react-router-dom'
import { useAsync } from '../../hooks/useAsync.js'
import { adminApi } from '../../services/api'
import {
  CHART_COLORS,
  PRIORITY_ORDER,
  PriorityBadge,
  formatDateTime,
  formatHours,
  formatPercent,
} from '../../utils/format.jsx'
import {
  Card,
  DataTable,
  DetailSkeleton,
  ErrorState,
  PageHeader,
  SkeletonStats,
  StatCard,
} from '../../components/ui.jsx'
import {
  ActivityIcon,
  AwardIcon,
  CheckCircleIcon,
  ClockIcon,
  LayersIcon,
  PrintIcon,
  TargetIcon,
  TicketIcon,
  UsersIcon,
} from '../../components/icons.jsx'
import {
  Area,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

const FALLBACK_COLOR = '#98a2b3'

function toChartData(counts = {}) {
  return Object.entries(counts).map(([name, value]) => ({ name, value }))
}

/** Shared Recharts chrome so all four charts read as one system. */
const axisProps = {
  stroke: CHART_COLORS.axis,
  tick: { fontSize: 11, fill: '#667085' },
  tickLine: false,
  axisLine: false,
}

const gridProps = {
  strokeDasharray: '3 3',
  stroke: CHART_COLORS.grid,
  vertical: false,
}

const tooltipProps = {
  cursor: { fill: 'rgba(74, 104, 245, 0.06)' },
  contentStyle: {
    borderRadius: 12,
    border: '1px solid #e6eaf2',
    boxShadow: '0 12px 28px -12px rgb(16 24 40 / 0.20)',
    fontSize: 12,
  },
}

const legendProps = {
  iconType: 'circle',
  iconSize: 8,
  wrapperStyle: { fontSize: 11, paddingTop: 8 },
}

function ChartCard({ title, subtitle, icon, children, height = 'h-72' }) {
  return (
    <Card title={title} subtitle={subtitle} icon={icon}>
      <div className={height}>{children}</div>
    </Card>
  )
}

/**
 * Analytics page.
 *
 * Every figure is a live aggregate from `analytics_service`; nothing here is
 * pre-baked. Charts use the same colour mapping as the badges so a category
 * keeps one colour across the whole product.
 */
export default function Analytics() {
  const { data, loading, error, reload } = useAsync(() => adminApi.analytics(), [])

  if (loading) {
    return (
      <>
        <SkeletonStats />
        <div className="mt-6">
          <DetailSkeleton cards={[2]} />
        </div>
      </>
    )
  }
  if (error) return <ErrorState error={error} onRetry={reload} />

  const summary = data?.summary ?? {}
  const sla = data?.sla ?? {}
  const byCategory = toChartData(data?.by_category)
  const byPriority = toChartData(data?.by_priority)
  const byStatus = toChartData(data?.by_status)
  const trend = (data?.volume_trend ?? []).map((point) => ({
    date: point.date.slice(5),
    tickets: point.count,
  }))
  const teams = data?.team_performance ?? []
  const agents = data?.agent_performance ?? []
  const matrix = data?.category_priority_matrix ?? []
  const notifications = data?.notifications ?? {}
  const users = data?.users ?? {}
  const priorities = PRIORITY_ORDER.filter((p) => matrix.some((row) => row.counts?.[p] !== undefined))

  return (
    <>
      <PageHeader
        eyebrow="Administration"
        title="Analytics & reports"
        description={`Live aggregates generated ${formatDateTime(data?.generated_at)}.`}
        actions={
          <button type="button" className="btn-secondary no-print" onClick={() => window.print()}>
            <PrintIcon className="h-4 w-4" />
            Print / save as PDF
          </button>
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
          label="Unresolved"
          value={summary.unresolved_tickets ?? 0}
          tone="warning"
          hint={`${summary.open_tickets ?? 0} open · ${summary.in_progress_tickets ?? 0} active`}
          icon={ClockIcon}
        />
        <StatCard
          label="Avg resolution"
          value={summary.avg_resolution_time_display ?? '—'}
          tone="success"
          icon={CheckCircleIcon}
          hint={
            summary.fastest_resolution_hours != null
              ? `Fastest ${formatHours(summary.fastest_resolution_hours)}`
              : undefined
          }
        />
        <StatCard
          label="SLA compliance"
          value={formatPercent(sla.sla_compliance_rate)}
          icon={TargetIcon}
          hint={`${sla.near_sla ?? 0} near breach · ${sla.open_breached ?? 0} breached`}
        />
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-2">
        <ChartCard
          title="Tickets by category"
          subtitle="DistilBERT classification totals"
          icon={LayersIcon}
        >
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie
                data={byCategory}
                dataKey="value"
                nameKey="name"
                outerRadius={100}
                innerRadius={55}
                paddingAngle={2}
                stroke="#fff"
                strokeWidth={2}
              >
                {byCategory.map((entry) => (
                  <Cell
                    key={entry.name}
                    fill={CHART_COLORS.category[entry.name] ?? FALLBACK_COLOR}
                  />
                ))}
              </Pie>
              <Tooltip {...tooltipProps} />
              <Legend {...legendProps} />
            </PieChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard
          title="Tickets by priority"
          subtitle="Rule-based priority distribution"
          icon={TargetIcon}
        >
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={byPriority} margin={{ top: 8, right: 8, left: -18, bottom: 0 }}>
              <CartesianGrid {...gridProps} />
              <XAxis dataKey="name" {...axisProps} />
              <YAxis allowDecimals={false} {...axisProps} />
              <Tooltip {...tooltipProps} cursor={{ fill: 'rgba(74, 104, 245, 0.06)' }} />
              <Bar dataKey="value" name="Tickets" radius={[6, 6, 0, 0]} maxBarSize={56}>
                {byPriority.map((entry) => (
                  <Cell
                    key={entry.name}
                    fill={CHART_COLORS.priority[entry.name] ?? FALLBACK_COLOR}
                  />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard title="Tickets by status" subtitle="Lifecycle distribution" icon={ActivityIcon}>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={byStatus} margin={{ top: 8, right: 8, left: -18, bottom: 0 }}>
              <CartesianGrid {...gridProps} />
              <XAxis dataKey="name" {...axisProps} />
              <YAxis allowDecimals={false} {...axisProps} />
              <Tooltip {...tooltipProps} cursor={{ fill: 'rgba(74, 104, 245, 0.06)' }} />
              <Bar dataKey="value" name="Tickets" radius={[6, 6, 0, 0]} maxBarSize={56}>
                {byStatus.map((entry) => (
                  <Cell key={entry.name} fill={CHART_COLORS.status[entry.name] ?? FALLBACK_COLOR} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard title="Ticket volume" subtitle="Last 14 days, zero-filled" icon={ActivityIcon}>
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={trend} margin={{ top: 8, right: 12, left: -18, bottom: 0 }}>
              <defs>
                <linearGradient id="volumeFill" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#4a68f5" stopOpacity={0.28} />
                  <stop offset="100%" stopColor="#4a68f5" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid {...gridProps} />
              <XAxis dataKey="date" {...axisProps} />
              <YAxis allowDecimals={false} {...axisProps} />
              <Tooltip {...tooltipProps} />
              <Area
                type="monotone"
                dataKey="tickets"
                stroke="none"
                fill="url(#volumeFill)"
                activeDot={false}
                legendType="none"
                tooltipType="none"
              />
              <Line
                type="monotone"
                dataKey="tickets"
                name="Tickets"
                stroke="#4a68f5"
                strokeWidth={2.5}
                dot={{ r: 2.5, strokeWidth: 0, fill: '#4a68f5' }}
                activeDot={{ r: 5 }}
              />
            </LineChart>
          </ResponsiveContainer>
        </ChartCard>
      </div>

      {/* ---- Category x priority matrix ---- */}
      <Card
        className="mt-6"
        title="Category × priority"
        subtitle="How severity distributes per category"
        icon={LayersIcon}
        bodyClass="p-0"
      >
        <div className="overflow-x-auto p-5 sm:p-6">
          <table className="table">
            <thead>
              <tr>
                <th scope="col">Category</th>
                {priorities.map((priority) => (
                  <th key={priority} scope="col" className="text-right">
                    {priority}
                  </th>
                ))}
                <th scope="col" className="text-right">
                  Total
                </th>
              </tr>
            </thead>
            <tbody>
              {matrix.map((row) => (
                <tr key={row.category}>
                  <td>
                    <span className="flex items-center gap-2">
                      <span
                        aria-hidden="true"
                        className="h-2.5 w-2.5 shrink-0 rounded-full"
                        style={{ background: CHART_COLORS.category[row.category] ?? FALLBACK_COLOR }}
                      />
                      <span className="font-semibold text-ink">{row.category}</span>
                    </span>
                  </td>
                  {priorities.map((priority) => (
                    <td key={priority} className="num">
                      <span
                        className={`inline-flex min-w-8 justify-center rounded-md px-1.5 py-0.5 ${
                          row.counts?.[priority]
                            ? 'bg-slate-100 font-semibold text-ink'
                            : 'text-ink-faint'
                        }`}
                      >
                        {row.counts?.[priority] ?? 0}
                      </span>
                    </td>
                  ))}
                  <td className="num font-bold text-ink">{row.total}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      <div className="mt-6 grid gap-6 lg:grid-cols-2">
        <Card
          title="Team performance"
          subtitle="From the live routing table"
          icon={UsersIcon}
          bodyClass="p-0"
        >
          <DataTable
            columns={[
              {
                key: 'team',
                header: 'Team',
                cellClassName: 'font-semibold text-ink',
                render: (t) => t.team,
              },
              {
                key: 'categories',
                header: 'Handles',
                cellClassName: 'text-xs text-ink-muted',
                render: (t) => (t.handles_categories ?? []).join(', '),
              },
              { key: 'total', header: 'Total', cellClassName: 'num', render: (t) => t.total_tickets },
              { key: 'open', header: 'Open', cellClassName: 'num', render: (t) => t.open },
              {
                key: 'urgent',
                header: 'Urgent',
                cellClassName: 'num font-semibold text-rose-600',
                render: (t) => t.urgent,
              },
              {
                key: 'rate',
                header: 'Resolved',
                cellClassName: 'num',
                render: (t) => formatPercent(t.resolution_rate, 0),
              },
            ]}
            rows={teams}
            rowKey={(t) => t.team}
          />
        </Card>

        <Card
          title="Agent leaderboard"
          subtitle="Resolved tickets and average handling time"
          icon={AwardIcon}
          bodyClass="p-0"
        >
          <DataTable
            columns={[
              {
                key: 'name',
                header: 'Agent',
                cellClassName: 'font-semibold text-ink',
                render: (a) => a.name,
              },
              { key: 'team', header: 'Team', render: (a) => a.team ?? '—' },
              {
                key: 'resolved',
                header: 'Resolved',
                cellClassName: 'num font-semibold text-ink',
                render: (a) => a.resolved_tickets,
              },
              {
                key: 'avg',
                header: 'Avg time',
                cellClassName: 'num',
                render: (a) =>
                  a.avg_resolution_hours != null ? formatHours(a.avg_resolution_hours) : '—',
              },
            ]}
            rows={agents}
            rowKey={(a) => a.user_id}
          />
        </Card>
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-2">
        <Card
          title="Platform counters"
          subtitle="Users, notifications and SLA windows"
          icon={ActivityIcon}
        >
          <dl className="grid gap-2.5 sm:grid-cols-2">
            <Counter label="Users total" value={users.total} />
            <Counter label="Active users" value={users.active} tone="success" />
            <Counter label="Employees" value={users.employee} />
            <Counter label="Agents" value={users.agent} />
            <Counter label="Administrators" value={users.admin} />
            {Object.entries(notifications).map(([type, count]) => (
              <Counter key={type} label={`Notifications · ${type}`} value={count} />
            ))}
          </dl>

          {sla?.config?.hours_per_priority && (
            <div className="mt-5 border-t border-hairline pt-5">
              <p className="micro-label mb-2.5">SLA configuration</p>
              <div className="space-y-1">
                {Object.entries(sla.config.hours_per_priority).map(([priority, hours]) => (
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
                <div className="flex items-center justify-between rounded-lg px-2 py-1.5 odd:bg-slate-50/70">
                  <dt className="text-[0.8125rem] text-ink-muted">Near-breach threshold</dt>
                  <dd className="font-semibold tabular-nums text-ink">
                    {formatPercent(sla.config.near_threshold_pct, 0)}
                  </dd>
                </div>
              </div>
            </div>
          )}
        </Card>

        <Card title="SLA health" subtitle="Live compliance snapshot" icon={TargetIcon}>
          <SlaHighlight rate={sla.sla_compliance_rate} />
          <dl className="mt-4 grid gap-2.5 sm:grid-cols-2">
            <Counter label="Compliant" value={sla.total_compliant ?? 0} tone="success" />
            <Counter label="Near breach" value={sla.near_sla ?? 0} tone="warning" />
            <Counter label="Breached (open)" value={sla.open_breached ?? 0} tone="danger" />
            <Counter label="Resolved late" value={sla.resolved_late ?? 0} tone="danger" />
          </dl>
        </Card>
      </div>

      <p className="mt-6 text-xs text-ink-muted">
        Figures are computed live from PostgreSQL by{' '}
        <code className="rounded bg-slate-100 px-1.5 py-0.5 font-mono">analytics_service</code>;
        refreshing this page re-queries the database.{' '}
        <Link
          to="/admin/ml"
          className="inline-flex items-center gap-1 font-semibold text-brand-700 hover:underline"
        >
          Check the ML engine status
        </Link>
        .
      </p>
    </>
  )
}

/** Large compliance figure with a matching progress bar. */
function SlaHighlight({ rate }) {
  const value = Number(rate ?? 0)
  const config =
    value >= 95
      ? { bg: 'bg-emerald-50 ring-emerald-100', bar: 'bg-emerald-500', text: 'text-emerald-700' }
      : value >= 85
        ? { bg: 'bg-amber-50 ring-amber-100', bar: 'bg-amber-500', text: 'text-amber-700' }
        : { bg: 'bg-rose-50 ring-rose-100', bar: 'bg-rose-500', text: 'text-rose-700' }

  return (
    <div className={`rounded-xl p-5 ring-1 ${config.bg}`}>
      <p className="micro-label">SLA compliance</p>
      <p className={`mt-1 text-4xl font-semibold tracking-tight tabular-nums ${config.text}`}>
        {formatPercent(rate)}
      </p>
      <div className="mt-3 h-2.5 w-full overflow-hidden rounded-full bg-white/70">
        <div
          className={`h-full rounded-full ${config.bar}`}
          style={{ width: `${Math.max(2, Math.min(100, value))}%` }}
        />
      </div>
    </div>
  )
}

/** Compact label/value tile used in the counter grids. */
function Counter({ label, value, tone = 'default' }) {
  const accents = {
    default: 'text-ink',
    success: 'text-emerald-600',
    warning: 'text-amber-600',
    danger: 'text-rose-600',
  }
  return (
    <div className="flex items-center justify-between gap-3 rounded-xl border border-hairline bg-slate-50/60 px-3.5 py-2.5">
      <dt className="truncate text-[0.8125rem] text-ink-muted">{label}</dt>
      <dd className={`shrink-0 text-[0.8125rem] font-bold tabular-nums ${accents[tone]}`}>
        {value ?? 0}
      </dd>
    </div>
  )
}
