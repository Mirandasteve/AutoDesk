import { Link, useNavigate, useParams } from 'react-router-dom'
import { useAsync } from '../../hooks/useAsync.js'
import { ticketApi } from '../../services/api'
import {
  CategoryBadge,
  PriorityBadge,
  SlaBadge,
  StatusBadge,
  formatDateTime,
  formatHours,
  formatRelative,
} from '../../utils/format.jsx'
import {
  Alert,
  Card,
  ConfidenceMeter,
  DetailList,
  DetailSkeleton,
  ErrorState,
  KeyValue,
  PageHeader,
  Timeline,
} from '../../components/ui.jsx'
import {
  ActivityIcon,
  ArrowLeftIcon,
  CheckCircleIcon,
  CpuIcon,
  FileTextIcon,
  PlusIcon,
  TargetIcon,
} from '../../components/icons.jsx'

/**
 * Employee view of one ticket.
 *
 * Read-only by design: `PATCH /api/tickets/<id>` and `POST .../notes` both
 * reject employees for the status, priority, assignment and resolution fields
 * (SRS section 38), so this screen shows the classification audit trail and the
 * notification history and offers no controls that would fail.
 */
export default function EmployeeTicketDetail() {
  const { id } = useParams()
  const navigate = useNavigate()
  const { data, loading, error, reload } = useAsync(() => ticketApi.get(id), [id])

  if (loading) return <DetailSkeleton cards={[2, 1]} />
  if (error) return <ErrorState error={error} onRetry={reload} />

  const ticket = data?.ticket
  if (!ticket) return <ErrorState error={{ message: 'Ticket not found.' }} />

  const events = ticket.notifications ?? []

  return (
    <>
      <PageHeader
        eyebrow={`Employee portal · Ticket #${ticket.id}`}
        title={ticket.title}
        description={`Raised ${formatRelative(ticket.created_at)} · ${ticket.assigned_team ?? 'awaiting routing'}`}
        actions={
          <>
            <Link to="/tickets/my" className="btn-secondary">
              <ArrowLeftIcon className="h-4 w-4" />
              Back to my tickets
            </Link>
            <button type="button" className="btn-primary" onClick={() => navigate('/tickets/new')}>
              <PlusIcon className="h-4 w-4" />
              Raise another
            </button>
          </>
        }
      >
        <div className="flex flex-wrap items-center gap-2">
          <StatusBadge value={ticket.status} />
          <PriorityBadge value={ticket.priority} />
          <CategoryBadge value={ticket.category} />
          <SlaBadge ticket={ticket} />
        </div>
      </PageHeader>

      {ticket.status === 'Resolved' && ticket.resolution_notes && (
        <div className="mb-6">
          <Alert tone="success" title="Resolution">
            {ticket.resolution_notes}
          </Alert>
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-2">
          <Card title="Description" icon={FileTextIcon}>
            <p className="whitespace-pre-wrap text-[0.9375rem] leading-relaxed text-ink-soft">
              {ticket.description}
            </p>
          </Card>

          <Card
            title="Activity"
            subtitle="Every notification raised for this ticket"
            icon={ActivityIcon}
          >
            <Timeline items={events} />
          </Card>
        </div>

        <div className="space-y-6">
          <Card
            title="Classification"
            subtitle="Real DistilBERT output stored with the ticket"
            icon={CpuIcon}
          >
            <ConfidenceMeter value={ticket.confidence} className="mb-4" />
            <DetailList>
              <KeyValue label="Category">{ticket.category}</KeyValue>
              <KeyValue label="Source">{ticket.classification_source ?? '-'}</KeyValue>
              <KeyValue label="Model" mono>
                {ticket.ml_model ?? '-'}
              </KeyValue>
            </DetailList>
            {ticket.priority_reason && (
              <div className="panel mt-4">
                <p className="micro-label">Why this priority</p>
                <p className="mt-1.5 text-[0.8125rem] leading-relaxed text-ink-soft">
                  {ticket.priority_reason}
                </p>
              </div>
            )}
          </Card>

          <Card title="Routing & SLA" subtitle="Set automatically by the pipeline" icon={TargetIcon}>
            <DetailList>
              <KeyValue label="Assigned team">{ticket.assigned_team}</KeyValue>
              <KeyValue label="Assigned agent">{ticket.assignee?.name ?? 'Unassigned'}</KeyValue>
              <KeyValue label="SLA window">{formatHours(ticket.sla_hours)}</KeyValue>
              <KeyValue label="SLA due">{formatDateTime(ticket.sla_due_at)}</KeyValue>
              {ticket.status !== 'Resolved' && (
                <KeyValue label="Time remaining">
                  {ticket.sla_breached ? (
                    <span className="text-rose-600">Breached</span>
                  ) : (
                    formatHours(ticket.sla_remaining_hours)
                  )}
                </KeyValue>
              )}
              {ticket.resolution_hours != null && (
                <KeyValue label="Time to resolve">
                  {formatHours(ticket.resolution_hours)}
                </KeyValue>
              )}
              {ticket.status === 'Resolved' && (
                <KeyValue label="Resolved">
                  <span className="inline-flex items-center gap-1.5 text-emerald-700">
                    <CheckCircleIcon className="h-4 w-4" />
                    {formatDateTime(ticket.resolved_at)}
                  </span>
                </KeyValue>
              )}
            </DetailList>
          </Card>
        </div>
      </div>
    </>
  )
}
