import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useAsync } from '../../hooks/useAsync.js'
import { adminApi } from '../../services/api'
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
  CpuIcon,
  FileTextIcon,
  RefreshIcon,
  SparklesIcon,
  TargetIcon,
} from '../../components/icons.jsx'

/**
 * Admin inspection view for one ticket.
 *
 * Adds the re-classify control (POST /api/admin/reclassify/<id>), which re-runs
 * the live pipeline and stores the new result. It is deliberately exposed here
 * so a reviewer can see the stored category come out of the model rather than
 * assume it.
 */
export default function AdminTicketDetail() {
  const { id } = useParams()
  const { data, loading, error, reload } = useAsync(() => adminApi.ticket(id), [id])

  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState(null)
  const [actionError, setActionError] = useState(null)

  async function reclassify(updatePriority) {
    setBusy(true)
    setActionError(null)
    try {
      const result = await adminApi.reclassify(id, updatePriority)
      setNotice(result.message)
      await reload()
    } catch (err) {
      setActionError(err.message)
    } finally {
      setBusy(false)
    }
  }

  if (loading) return <DetailSkeleton cards={[2, 1]} />
  if (error) return <ErrorState error={error} onRetry={reload} />

  const ticket = data?.ticket
  if (!ticket) return <ErrorState error={{ message: 'Ticket not found.' }} />

  const events = ticket.notifications ?? []

  return (
    <>
      <PageHeader
        eyebrow={`Administration · Ticket #${ticket.id}`}
        title={ticket.title}
        description={`Raised by ${ticket.creator?.name ?? 'unknown'} ${formatRelative(ticket.created_at)} · routed to ${ticket.assigned_team ?? 'no team'}`}
        actions={
          <>
            <Link to="/admin/tickets" className="btn-secondary">
              <ArrowLeftIcon className="h-4 w-4" />
              Back to tickets
            </Link>
            <button
              type="button"
              className="btn-secondary"
              onClick={() => reclassify(false)}
              disabled={busy}
              title="Re-run DistilBERT and the routing engine, storing the new category"
            >
              <SparklesIcon className="h-4 w-4" />
              {busy ? 'Reclassifying…' : 'Reclassify'}
            </button>
            <button
              type="button"
              className="btn-primary"
              onClick={() => reclassify(true)}
              disabled={busy}
              title="Re-run the whole pipeline, including the priority engine"
            >
              <RefreshIcon className="h-4 w-4" />
              Reclassify + reprioritise
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

      {notice && (
        <div className="mb-5">
          <Alert tone="success" onDismiss={() => setNotice(null)}>
            {notice}
          </Alert>
        </div>
      )}
      {actionError && (
        <div className="mb-5">
          <Alert tone="danger" title="Action failed" onDismiss={() => setActionError(null)}>
            {actionError}
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

          {ticket.resolution_notes && (
            <Card title="Resolution notes">
              <p className="whitespace-pre-wrap text-[0.9375rem] leading-relaxed text-ink-soft">
                {ticket.resolution_notes}
              </p>
            </Card>
          )}

          <Card
            title="Notification history"
            subtitle="Every event recorded for this ticket"
            icon={ActivityIcon}
          >
            <Timeline items={events} empty="No notifications recorded." />
          </Card>
        </div>

        <div className="space-y-6">
          <Card title="ML classification" subtitle="As stored on the ticket" icon={CpuIcon}>
            <ConfidenceMeter value={ticket.confidence} className="mb-4" />
            <DetailList>
              <KeyValue label="Category">{ticket.category}</KeyValue>
              <KeyValue label="Source">{ticket.classification_source ?? '-'}</KeyValue>
              <KeyValue label="Model" mono>
                {ticket.ml_model ?? '-'}
              </KeyValue>
            </DetailList>
          </Card>

          <Card title="Priority decision" icon={TargetIcon}>
            <p className="text-[0.8125rem] leading-relaxed text-ink-soft">
              {ticket.priority_reason ?? 'No reason recorded.'}
            </p>
          </Card>

          <Card title="Ownership & SLA" icon={TargetIcon}>
            <DetailList>
              <KeyValue label="Employee">{ticket.creator?.name ?? '-'}</KeyValue>
              <KeyValue label="Assigned team">{ticket.assigned_team}</KeyValue>
              <KeyValue label="Assignee">{ticket.assignee?.name ?? 'Unassigned'}</KeyValue>
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
              <KeyValue label="Resolved at">{formatDateTime(ticket.resolved_at)}</KeyValue>
            </DetailList>
          </Card>
        </div>
      </div>
    </>
  )
}
