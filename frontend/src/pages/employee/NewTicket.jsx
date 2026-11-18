import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAsync, useDebounced } from '../../hooks/useAsync.js'
import { metaApi, ticketApi } from '../../services/api'
import { PriorityBadge } from '../../utils/format.jsx'
import {
  Alert,
  Card,
  EmptyState,
  ErrorState,
  Field,
  PageHeader,
  Progress,
  Select,
  Spinner,
  TextArea,
  TextInput,
} from '../../components/ui.jsx'
import {
  ArrowLeftIcon,
  ClockIcon,
  LayersIcon,
  SendIcon,
  SparklesIcon,
  TargetIcon,
} from '../../components/icons.jsx'

const PREVIEW_TIMEOUT_MS = 500
const PREVIEW_MIN_CHARS = 10

export default function EmployeeNewTicket() {
  const navigate = useNavigate()
  const { data: meta } = useAsync(() => metaApi.get(), [])
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [errors, setErrors] = useState({})
  const [formError, setFormError] = useState(null)
  const [submitting, setSubmitting] = useState(false)
  const [preview, setPreview] = useState(null)
  const [previewError, setPreviewError] = useState(null)
  const [previewing, setPreviewing] = useState(false)

  const debouncedDesc = useDebounced(description, 350)
  const debouncedTitle = useDebounced(title, 350)

  // Live preview: call POST /api/tickets/lookup so the employee sees DistilBERT
  // category, priority, team and confidence *before* they submit. This uses the
  // same pipeline as actual ticket creation, so the preview cannot drift.
  useEffect(() => {
    const combined = debouncedDesc.trim()
    if (combined.length < PREVIEW_MIN_CHARS) {
      setPreview(null)
      setPreviewError(null)
      return undefined
    }
    let cancelled = false
    const timer = setTimeout(async () => {
      try {
        setPreviewing(true)
        setPreviewError(null)
        const data = await ticketApi.lookup(debouncedDesc, debouncedTitle)
        if (!cancelled) setPreview(data)
      } catch (err) {
        if (!cancelled) {
          setPreviewError(err.message)
          setPreview(null)
        }
      } finally {
        if (!cancelled) setPreviewing(false)
      }
    }, PREVIEW_TIMEOUT_MS)
    return () => {
      cancelled = true
      clearTimeout(timer)
    }
  }, [debouncedDesc, debouncedTitle])

  async function onSubmit(event) {
    event.preventDefault()
    setErrors({})
    setFormError(null)
    setSubmitting(true)
    try {
      const result = await ticketApi.create({ title: title.trim(), description: description.trim() })
      const id = result.ticket?.id
      navigate(id ? `/tickets/${id}` : '/tickets/my', { replace: true })
    } catch (err) {
      setFormError(err.message)
      setErrors(err.fields ?? {})
    } finally {
      setSubmitting(false)
    }
  }

  const readyToPreview = description.trim().length >= PREVIEW_MIN_CHARS
  const topCandidates = preview?.top_k?.slice(0, 3) ?? []

  return (
    <>
      <PageHeader
        eyebrow="Employee portal"
        title="Raise a new ticket"
        description="Describe the problem clearly. The model will classify and route it automatically."
        actions={
          <Link to="/dashboard" className="btn-secondary">
            <ArrowLeftIcon className="h-4 w-4" />
            Back to dashboard
          </Link>
        }
      />

      <div className="grid gap-6 lg:grid-cols-3">
        <Card className="lg:col-span-2" title="Ticket details" icon={LayersIcon}>
          <form onSubmit={onSubmit} className="space-y-5">
            <Field
              label="Title"
              htmlFor="title"
              required
              error={errors.title}
              hint="A short, specific headline — this carries most of the classification signal."
            >
              <TextInput
                id="title"
                placeholder="e.g. VPN not connecting from home"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                minLength={5}
                required
              />
            </Field>

            <Field
              label="Description"
              htmlFor="description"
              required
              error={errors.description}
              hint={`Include what happened, where, when and any steps you've tried. ${description.trim().length}/${PREVIEW_MIN_CHARS} characters minimum.`}
            >
              <TextArea
                id="description"
                rows={8}
                placeholder="Describe the issue in detail so the DistilBERT classifier can pick the right category."
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                minLength={PREVIEW_MIN_CHARS}
                required
              />
            </Field>

            {formError && (
              <Alert tone="danger" title="Could not create ticket">
                {formError}
              </Alert>
            )}

            <div className="flex flex-wrap items-center gap-3 border-t border-hairline pt-5">
              <button type="submit" className="btn-primary" disabled={submitting}>
                <SendIcon className="h-4 w-4" />
                {submitting ? 'Creating ticket…' : 'Submit ticket'}
              </button>
              <p className="text-xs text-ink-muted">
                Submitting runs the full pipeline and notifies the assigned team.
              </p>
            </div>
          </form>
        </Card>

        <div className="space-y-6">
          {/* ---- Live classification preview ---- */}
          <Card
            title="AI preview"
            subtitle="Computed live from your description"
            icon={SparklesIcon}
            bodyClass="p-5"
          >
            {!readyToPreview && (
              <EmptyState
                icon={SparklesIcon}
                title="Start typing"
                description={`Enter at least ${PREVIEW_MIN_CHARS} characters and the predicted category, priority and team appear here instantly.`}
              />
            )}

            {readyToPreview && previewing && !preview && (
              <div className="py-6 text-center">
                <Spinner label="Analysing" />
              </div>
            )}

            {readyToPreview && previewError && (
              <ErrorState error={{ message: previewError }} />
            )}

            {preview && (
              <div className="animate-fade-up space-y-4">
                <div className="rounded-xl bg-brand-gradient p-4 text-white shadow-card-md">
                  <p className="text-[0.6875rem] font-semibold uppercase tracking-[0.08em] text-white/70">
                    Predicted category
                  </p>
                  <p className="mt-1 text-lg font-semibold tracking-tight">{preview.category}</p>
                  <p className="mt-0.5 text-xs text-white/70">
                    {preview.classification_source}
                    {preview.top_k?.length > 0 && ' · top-k inference'}
                  </p>
                </div>

                <div className="panel">
                  <p className="micro-label">Priority</p>
                  <div className="mt-2">
                    <PriorityBadge value={preview.priority} />
                  </div>
                </div>

                <div className="panel">
                  <p className="micro-label">Assigned team</p>
                  <p className="mt-1.5 text-sm font-semibold text-ink">{preview.assigned_team}</p>
                </div>

                {topCandidates.length > 0 && (
                  <div>
                    <p className="micro-label mb-2.5">Top candidates</p>
                    <div className="space-y-2.5">
                      {topCandidates.map((candidate) => (
                        <Progress
                          key={candidate.category}
                          label={candidate.category}
                          value={Math.round((candidate.confidence ?? 0) * 100)}
                          tone={candidate.category === preview.category ? 'brand' : 'accent'}
                        />
                      ))}
                    </div>
                  </div>
                )}

                {previewing && (
                  <p className="text-center text-xs text-ink-faint">Re-analysing as you type…</p>
                )}
              </div>
            )}
          </Card>

          {meta?.sla_hours && (
            <Card
              title="SLA targets"
              subtitle="Applied automatically once the priority is set"
              icon={TargetIcon}
            >
              <dl className="space-y-1">
                {Object.entries(meta.sla_hours).map(([priority, hours]) => (
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
              <p className="mt-3 flex items-start gap-1.5 text-xs leading-relaxed text-ink-faint">
                <ClockIcon className="mt-px h-3.5 w-3.5 shrink-0" />
                You will be notified automatically as the deadline approaches.
              </p>
            </Card>
          )}
        </div>
      </div>
    </>
  )
}
