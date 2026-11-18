import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useAsync } from '../../hooks/useAsync.js'
import { agentApi } from '../../services/api'
import { useAuth } from '../../context/AuthContext.jsx'
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
  Field,
  KeyValue,
  Modal,
  PageHeader,
  Select,
  TextArea,
  Timeline,
} from '../../components/ui.jsx'
import {
  ActivityIcon,
  ArrowLeftIcon,
  CheckCircleIcon,
  CpuIcon,
  FileTextIcon,
  HandIcon,
  TargetIcon,
} from '../../components/icons.jsx'

/**
 * Agent workspace for one ticket.
 *
 * The two actions an agent owns (SRS section 14):
 *   * claim  -> POST /api/agent/tickets/<id>/claim
 *   * status -> PATCH /api/agent/tickets/<id>/status
 *
 * `Resolved` requires resolution notes, which the backend enforces; the form
 * makes the same requirement visible before submission rather than bouncing the
 * user off a 422.
 */
export default function AgentTicketDetail() {
  const { id } = useParams()
  const { user } = useAuth()
  const { data, loading, error, reload } = useAsync(() => agentApi.get(id), [id])

  const [statusOpen, setStatusOpen] = useState(false)
  const [nextStatus, setNextStatus] = useState('In Progress')
  const [notes, setNotes] = useState('')
  const [busy, setBusy] = useState(false)
  const [actionError, setActionError] = useState(null)
  const [notice, setNotice] = useState(null)

  async function claim() {
    setBusy(true)
    setActionError(null)
    try {
      const result = await agentApi.claim(id)
      setNotice(result.message ?? 'Ticket assigned to you.')
      await reload()
    } catch (err) {
      setActionError(err.message)
    } finally {
      setBusy(false)
    }
  }

  async function submitStatus(event) {
    event.preventDefault()
    setBusy(true)
    setActionError(null)
    try {
      const payload = { status: nextStatus }
      // The backend rejects "Resolved" without notes, so only send them when
      // they are actually required.
      if (nextStatus === 'Resolved') payload.resolution_notes = notes.trim()
      const result = await agentApi.setStatus(id, payload)
      setNotice(result.message ?? 'Status updated.')
      setStatusOpen(false)
      setNotes('')
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

  const allowedStatuses = data?.allowed_statuses ?? ['Open', 'In Progress', 'Resolved']
  const mine = ticket.assigned_to === user?.id
  const events = ticket.notifications ?? []

  return (
    <>
      <PageHeader
        eyebrow={`Support desk · Ticket #${ticket.id}`}
        title={ticket.title}
        description={`Raised by ${ticket.creator?.name ?? 'unknown'} ${formatRelative(ticket.created_at)} · routed to ${ticket.assigned_team ?? 'no team'}`}
        actions={
          <>
            <Link to="/agent/tickets" className="btn-secondary">
              <ArrowLeftIcon className="h-4 w-4" />
              Back to queue
            </Link>
            {!mine && ticket.status !== 'Resolved' && (
              <button type="button" className="btn-primary" onClick={claim} disabled={busy}>
                <HandIcon className="h-4 w-4" />
                {busy ? 'Claiming…' : 'Claim ticket'}
              </button>
            )}
            {mine && ticket.status !== 'Resolved' && (
              <button
                type="button"
                className="btn-primary"
                onClick={() => {
                  setNextStatus(ticket.status === 'Open' ? 'In Progress' : 'Resolved')
                  setStatusOpen(true)
                }}
              >
                <CheckCircleIcon className="h-4 w-4" />
                Update status
              </button>
            )}
          </>
        }
      >
        <div className="flex flex-wrap items-center gap-2">
          <StatusBadge value={ticket.status} />
          <PriorityBadge value={ticket.priority} />
          <CategoryBadge value={ticket.category} />
          <SlaBadge ticket={ticket} />
          {mine && <span className="badge badge-soft badge-ok">Assigned to you</span>}
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
            <Card title="Resolution notes" icon={CheckCircleIcon}>
              <p className="whitespace-pre-wrap text-[0.9375rem] leading-relaxed text-ink-soft">
                {ticket.resolution_notes}
              </p>
            </Card>
          )}

          <Card
            title="Activity"
            subtitle="Status changes and notifications"
            icon={ActivityIcon}
          >
            <Timeline items={events} />
          </Card>
        </div>

        <div className="space-y-6">
          <Card
            title="Classification"
            subtitle="What the model decided, and how sure it was"
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

          <Card title="Routing & SLA" icon={TargetIcon}>
            <DetailList>
              <KeyValue label="Assigned team">{ticket.assigned_team}</KeyValue>
              <KeyValue label="Assignee">{ticket.assignee?.name ?? 'Unassigned'}</KeyValue>
              <KeyValue label="Employee">{ticket.creator?.name ?? '-'}</KeyValue>
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
            </DetailList>
          </Card>
        </div>
      </div>

      <Modal
        open={statusOpen}
        title={`Update ticket #${ticket.id}`}
        onClose={() => setStatusOpen(false)}
        footer={
          <>
            <button type="button" className="btn-secondary" onClick={() => setStatusOpen(false)}>
              Cancel
            </button>
            <button
              type="submit"
              form="status-form"
              className="btn-primary"
              disabled={busy || (nextStatus === 'Resolved' && notes.trim().length < 3)}
            >
              {busy ? 'Saving…' : 'Save status'}
            </button>
          </>
        }
      >
        <form id="status-form" onSubmit={submitStatus} className="space-y-4">
          <Field label="New status" htmlFor="status">
            <Select id="status" value={nextStatus} onChange={(e) => setNextStatus(e.target.value)}>
              {allowedStatuses.map((status) => (
                <option key={status} value={status} disabled={status === ticket.status}>
                  {status}
                  {status === ticket.status ? ' (current)' : ''}
                </option>
              ))}
            </Select>
          </Field>

          {nextStatus === 'Resolved' && (
            <Field
              label="Resolution notes"
              htmlFor="resolution"
              required
              hint="Required to close a ticket. The employee is notified with these notes."
            >
              <TextArea
                id="resolution"
                rows={5}
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                placeholder="What was the root cause and what fixed it?"
                required
              />
            </Field>
          )}
        </form>
      </Modal>
    </>
  )
}
