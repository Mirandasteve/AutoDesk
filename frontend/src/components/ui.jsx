/**
 * Reusable presentational building blocks.
 *
 * These are deliberately dumb: they render what the API returned and never
 * invent a value. Anything derived (counts, SLA verdicts, category labels)
 * already arrives computed from the backend.
 *
 * Everything visual is defined once here and in `src/index.css`, so a change to
 * the component layer restyles all nineteen screens at once.
 */
import { useEffect } from 'react'
import {
  AlertCircleIcon,
  AlertTriangleIcon,
  CheckCircleIcon,
  ChevronLeftIcon,
  ChevronRightIcon,
  CloseIcon,
  InboxIcon,
  InfoIcon,
  SearchIcon,
} from './icons.jsx'

// ---------------------------------------------------------------------------
// Tone maps
// ---------------------------------------------------------------------------
const TONE_ICON = {
  brand: { text: 'text-brand-700', bg: 'bg-brand-50', ring: 'ring-brand-100' },
  accent: { text: 'text-accent-700', bg: 'bg-accent-50', ring: 'ring-accent-100' },
  success: { text: 'text-emerald-700', bg: 'bg-emerald-50', ring: 'ring-emerald-100' },
  warning: { text: 'text-amber-700', bg: 'bg-amber-50', ring: 'ring-amber-100' },
  danger: { text: 'text-rose-700', bg: 'bg-rose-50', ring: 'ring-rose-100' },
  neutral: { text: 'text-slate-600', bg: 'bg-slate-100', ring: 'ring-slate-200' },
}

/** Soft tinted container used for a stat card, a chart legend dot or an icon. */
export function IconTile({ icon: Icon, tone = 'brand', size = 'md', className = '' }) {
  const sizes = {
    sm: 'h-8 w-8 rounded-lg',
    md: 'h-10 w-10 rounded-xl',
    lg: 'h-12 w-12 rounded-2xl',
  }
  const glyphs = { sm: 'h-4 w-4', md: 'h-5 w-5', lg: 'h-6 w-6' }
  const tones = TONE_ICON[tone] ?? TONE_ICON.neutral
  return (
    <span
      aria-hidden="true"
      className={`inline-flex shrink-0 items-center justify-center ring-1 ${sizes[size]} ${tones.bg} ${tones.text} ${tones.ring} ${className}`}
    >
      {Icon && <Icon className={glyphs[size]} />}
    </span>
  )
}

// ---------------------------------------------------------------------------
// Layout
// ---------------------------------------------------------------------------
export function Card({
  title,
  subtitle,
  actions,
  icon,
  children,
  className = '',
  bodyClass = 'p-5 sm:p-6',
  footer,
}) {
  return (
    <section className={`card ${className}`}>
      {(title || actions) && (
        <header className="card-header">
          <div className="flex min-w-0 items-start gap-3">
            {icon && <IconTile icon={icon} size="sm" />}
            <div className="min-w-0">
              {title && <h2 className="card-title">{title}</h2>}
              {subtitle && <p className="card-subtitle">{subtitle}</p>}
            </div>
          </div>
          {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
        </header>
      )}
      <div className={bodyClass}>{children}</div>
      {footer && <div className="border-t border-hairline px-5 py-3 sm:px-6">{footer}</div>}
    </section>
  )
}

/**
 * Page title block.
 *
 * `eyebrow` is the small label above the title (portal name, section, or a
 * status), which keeps long ticket titles readable on ticket detail screens.
 */
export function PageHeader({ title, description, eyebrow, icon, actions, children }) {
  return (
    <div className="mb-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex min-w-0 items-start gap-3.5">
          {icon && <IconTile icon={icon} size="lg" className="mt-0.5" />}
          <div className="min-w-0">
            {eyebrow && <p className="micro-label mb-1.5">{eyebrow}</p>}
            <h1 className="text-2xl font-semibold tracking-tight text-ink sm:text-[1.75rem]">
              {title}
            </h1>
            {description && (
              <p className="mt-1.5 max-w-2xl text-sm leading-relaxed text-ink-muted">
                {description}
              </p>
            )}
          </div>
        </div>
        {actions && <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>}
      </div>
      {children && <div className="mt-5">{children}</div>}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Stats
// ---------------------------------------------------------------------------
export function StatCard({ label, value, hint, tone = 'default', icon }) {
  const tones = {
    default: 'border-hairline',
    brand: 'border-brand-200/80 bg-brand-50/50',
    accent: 'border-accent-200/80 bg-accent-50/50',
    success: 'border-emerald-200/80 bg-emerald-50/50',
    warning: 'border-amber-200/80 bg-amber-50/50',
    danger: 'border-rose-200/80 bg-rose-50/50',
  }
  const iconTone = tone === 'default' ? 'neutral' : tone
  return (
    <div className={`card border p-5 ${tones[tone] ?? tones.default}`}>
      <div className="flex items-start justify-between gap-3">
        <p className="text-[0.8125rem] font-medium text-ink-muted">{label}</p>
        {icon && <IconTile icon={icon} tone={iconTone} size="sm" />}
      </div>
      <p className="mt-3 text-[1.75rem] font-semibold leading-none tracking-tight tabular-nums text-ink">
        {value}
      </p>
      {hint && <p className="mt-2 text-xs leading-snug text-ink-muted">{hint}</p>}
    </div>
  )
}

/**
 * Slim labelled progress bar.
 *
 * Used for the classifier's top-k distribution and any 0–100 percentage that
 * benefits from seeing the magnitude next to the number.
 */
export function Progress({ value, tone = 'brand', label, showValue = true, className = '' }) {
  const pct = Math.max(0, Math.min(100, Number(value) || 0))
  const fills = {
    brand: 'bg-brand-gradient',
    success: 'bg-emerald-500',
    warning: 'bg-amber-500',
    danger: 'bg-rose-500',
    accent: 'bg-accent-500',
  }
  return (
    <div className={className}>
      {(label || showValue) && (
        <div className="mb-1.5 flex items-center justify-between gap-3 text-xs">
          {label && <span className="truncate text-ink-muted">{label}</span>}
          {showValue && <span className="font-semibold tabular-nums text-ink">{pct.toFixed(0)}%</span>}
        </div>
      )}
      <div
        className="h-1.5 w-full overflow-hidden rounded-full bg-slate-200"
        role="progressbar"
        aria-valuenow={pct}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={typeof label === 'string' ? label : undefined}
      >
        <div
          className={`h-full rounded-full ${fills[tone] ?? fills.brand} transition-[width] duration-500 ease-smooth`}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Loading
// ---------------------------------------------------------------------------
export function Spinner({ label = 'Loading' }) {
  return (
    <div className="flex items-center justify-center gap-3 py-14 text-sm text-ink-muted">
      <span className="h-4 w-4 animate-spin rounded-full border-2 border-slate-200 border-t-brand-600" />
      {label}…
    </div>
  )
}

/** Full-screen loader used while the session is being restored. */
export function ScreenLoader({ label = 'Loading AutoDesk' }) {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-4 bg-canvas">
      <span className="h-7 w-7 animate-spin rounded-full border-[3px] border-slate-200 border-t-brand-600" />
      <p className="text-sm text-ink-muted">{label}…</p>
    </div>
  )
}

export function Skeleton({ className = '' }) {
  return <div className={`skeleton ${className}`} />
}

/** Placeholder that matches the StatCard grid, so the layout never jumps. */
export function SkeletonStats({ count = 4 }) {
  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
      {Array.from({ length: count }, (_, index) => (
        <div key={index} className="card p-5">
          <Skeleton className="h-3.5 w-24" />
          <Skeleton className="mt-4 h-7 w-16" />
          <Skeleton className="mt-3 h-3 w-28" />
        </div>
      ))}
    </div>
  )
}

/** Placeholder that matches DataTable's row rhythm. */
export function SkeletonTable({ rows = 6, cols = 5 }) {
  return (
    <div className="space-y-3 p-5 sm:p-6">
      {Array.from({ length: rows }, (_, rowIndex) => (
        <div key={rowIndex} className="flex items-center gap-4">
          {Array.from({ length: cols }, (_, colIndex) => (
            <Skeleton
              key={colIndex}
              className={`h-3.5 ${colIndex === 1 ? 'flex-[2]' : 'flex-1'}`}
            />
          ))}
        </div>
      ))}
    </div>
  )
}

/**
 * Placeholder that matches a vertical feed of rows (notifications, activity),
 * each with an icon tile, a title and two lines of body copy.
 */
export function SkeletonList({ rows = 5 }) {
  return (
    <div className="card divide-y divide-hairline">
      {Array.from({ length: rows }, (_, index) => (
        <div key={index} className="flex gap-4 px-4 py-4 sm:px-5">
          <Skeleton className="h-9 w-9 shrink-0 rounded-xl" />
          <div className="min-w-0 flex-1 space-y-2.5 py-1">
            <Skeleton className="h-3.5 w-2/5" />
            <Skeleton className="h-3 w-full" />
            <Skeleton className="h-3 w-1/4" />
          </div>
        </div>
      ))}
    </div>
  )
}

/**
 * Two-column placeholder used by the ticket detail screens, so the page does not
 * jump from a spinner straight to content.
 */
export function DetailSkeleton({ cards = [2, 1] }) {
  return (
    <div className="grid gap-6 lg:grid-cols-3">
      {cards.map((span, index) => (
        <div
          key={index}
          className={`card space-y-4 p-5 sm:p-6 ${span === 2 ? 'lg:col-span-2' : ''}`}
        >
          <div className="skeleton h-4 w-36" />
          <div className="skeleton h-3 w-full" />
          <div className="skeleton h-3 w-11/12" />
          <div className="skeleton h-3 w-3/4" />
          <div className="skeleton h-3 w-1/2" />
        </div>
      ))}
    </div>
  )
}

// ---------------------------------------------------------------------------
// States
// ---------------------------------------------------------------------------
export function ErrorState({ error, onRetry }) {
  if (!error) return null
  return (
    <div className="rounded-2xl border border-rose-200 bg-rose-50/70 p-6">
      <div className="flex items-start gap-3.5">
        <IconTile icon={AlertTriangleIcon} tone="danger" size="sm" />
        <div className="min-w-0 flex-1">
          <p className="text-sm font-semibold text-rose-900">Something went wrong</p>
          <p className="mt-1 break-words text-sm text-rose-700">{error.message}</p>
          {onRetry && (
            <button type="button" onClick={onRetry} className="btn-secondary btn-sm mt-4">
              Try again
            </button>
          )}
        </div>
      </div>
    </div>
  )
}

export function EmptyState({ title, description, action, icon: Icon = InboxIcon }) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 px-6 py-14 text-center">
      <span className="flex h-14 w-14 items-center justify-center rounded-2xl bg-slate-100 text-slate-400 ring-1 ring-slate-200/70">
        <Icon className="h-6 w-6" />
      </span>
      <p className="text-sm font-semibold text-ink">{title}</p>
      {description && (
        <p className="max-w-md text-sm leading-relaxed text-ink-muted">{description}</p>
      )}
      {action && <div className="mt-2">{action}</div>}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Feedback
// ---------------------------------------------------------------------------
const ALERT_TONES = {
  info: {
    wrap: 'border-brand-200 bg-brand-50/80 text-brand-900',
    icon: InfoIcon,
    iconClass: 'text-brand-600',
  },
  success: {
    wrap: 'border-emerald-200 bg-emerald-50/80 text-emerald-900',
    icon: CheckCircleIcon,
    iconClass: 'text-emerald-600',
  },
  warning: {
    wrap: 'border-amber-200 bg-amber-50/80 text-amber-900',
    icon: AlertTriangleIcon,
    iconClass: 'text-amber-600',
  },
  danger: {
    wrap: 'border-rose-200 bg-rose-50/80 text-rose-900',
    icon: AlertCircleIcon,
    iconClass: 'text-rose-600',
  },
}

/** Accessible dismissible banner. */
export function Alert({ tone = 'info', title, children, onDismiss }) {
  const config = ALERT_TONES[tone] ?? ALERT_TONES.info
  const Icon = config.icon
  return (
    <div role="status" className={`flex items-start gap-3 rounded-xl border p-4 ${config.wrap}`}>
      <Icon className={`mt-0.5 h-4 w-4 shrink-0 ${config.iconClass}`} />
      <div className="min-w-0 flex-1">
        {title && <p className="text-sm font-semibold">{title}</p>}
        {children && <div className={`text-sm leading-relaxed ${title ? 'mt-1' : ''}`}>{children}</div>}
      </div>
      {onDismiss && (
        <button
          type="button"
          onClick={onDismiss}
          className="-m-1 shrink-0 rounded-lg p-1 opacity-60 transition hover:bg-black/5 hover:opacity-100"
          aria-label="Dismiss"
        >
          <CloseIcon className="h-4 w-4" />
        </button>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Form fields
// ---------------------------------------------------------------------------
export function Field({ label, htmlFor, error, hint, required, children }) {
  return (
    <div>
      <label className="label" htmlFor={htmlFor}>
        {label}
        {required && (
          <span className="ml-0.5 text-rose-500" aria-hidden="true">
            *
          </span>
        )}
      </label>
      {children}
      {hint && !error && <p className="field-hint">{hint}</p>}
      {error && (
        <p className="field-error">
          <AlertCircleIcon className="mt-px h-3.5 w-3.5 shrink-0" />
          <span>{error}</span>
        </p>
      )}
    </div>
  )
}

const INVALID = 'border-rose-400 focus:border-rose-500 focus:ring-rose-500/15'

export function TextInput({ error, className = '', ...props }) {
  return (
    <input
      className={`input ${error ? INVALID : ''} ${className}`}
      aria-invalid={error ? 'true' : undefined}
      {...props}
    />
  )
}

export function TextArea({ error, className = '', ...props }) {
  return (
    <textarea
      className={`input resize-y ${error ? INVALID : ''} ${className}`}
      aria-invalid={error ? 'true' : undefined}
      {...props}
    />
  )
}

export function Select({ error, children, className = '', ...props }) {
  return (
    <select
      className={`select ${error ? INVALID : ''} ${className}`}
      aria-invalid={error ? 'true' : undefined}
      {...props}
    >
      {children}
    </select>
  )
}

/** Text input with a leading search glyph; used by every list filter bar. */
export function SearchInput(props) {
  return (
    <div className="relative">
      <SearchIcon className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-faint" />
      <TextInput {...props} className={`input-search ${props.className ?? ''}`} />
    </div>
  )
}

// ---------------------------------------------------------------------------
// Data display
// ---------------------------------------------------------------------------

/** One label/value line inside a detail list. */
export function KeyValue({ label, children, mono = false }) {
  return (
    <div className="flex items-start justify-between gap-4 py-2.5">
      <dt className="shrink-0 text-[0.8125rem] text-ink-muted">{label}</dt>
      <dd
        className={`min-w-0 break-words text-right text-[0.8125rem] font-semibold text-ink ${
          mono ? 'font-mono text-xs' : ''
        }`}
      >
        {children ?? '-'}
      </dd>
    </div>
  )
}

/** Wrapper that draws the hairlines between a set of KeyValue rows. */
export function DetailList({ children, className = '' }) {
  return <dl className={`divide-y divide-slate-100 ${className}`}>{children}</dl>
}

/**
 * Vertical event timeline used by the three ticket detail screens.
 * `items` are the notification records the API returns for a ticket.
 */
export function Timeline({ items = [], empty = 'No activity recorded yet.' }) {
  if (items.length === 0) {
    return <p className="py-2 text-sm text-ink-muted">{empty}</p>
  }
  return (
    <ol className="relative space-y-5 before:absolute before:bottom-2 before:left-[5px] before:top-2 before:w-px before:bg-slate-200">
      {items.map((event) => (
        <li key={event.id} className="relative flex gap-3.5">
          <span
            aria-hidden="true"
            className="relative z-10 mt-1.5 h-2.5 w-2.5 shrink-0 rounded-full bg-brand-500 ring-4 ring-white"
          />
          <div className="min-w-0 flex-1">
            <p className="text-sm font-semibold leading-snug text-ink">{event.title}</p>
            {event.message && (
              <p className="mt-1 text-sm leading-relaxed text-ink-soft">{event.message}</p>
            )}
            <p className="mt-1.5 text-xs text-ink-faint">{formatEventTime(event.created_at)}</p>
          </div>
        </li>
      ))}
    </ol>
  )
}

function formatEventTime(value) {
  if (!value) return '-'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '-'
  return date.toLocaleString(undefined, {
    year: 'numeric',
    month: 'short',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

/**
 * Table.
 *
 * Columns are `{ key, header, render(row), className?, cellClassName? }`.
 * `stickyHeader` keeps the header visible inside the card's scroll area.
 */
export function DataTable({
  columns,
  rows,
  empty,
  onRowClick,
  rowKey = (row) => row.id,
  dense = false,
}) {
  if (!rows || rows.length === 0) {
    return empty ?? <EmptyState title="Nothing to show yet" />
  }
  const cellPadding = dense ? 'px-4 py-2' : 'px-4 py-3'
  return (
    <div className="overflow-x-auto">
      <table className="table">
        <thead>
          <tr>
            {columns.map((column) => (
              <th key={column.key} scope="col" className={column.className ?? ''}>
                {column.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr
              key={rowKey(row)}
              onClick={onRowClick ? () => onRowClick(row) : undefined}
              className={onRowClick ? 'clickable' : ''}
            >
              {columns.map((column) => (
                <td key={column.key} className={`${cellPadding} ${column.cellClassName ?? ''}`}>
                  {column.render(row)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Modal
// ---------------------------------------------------------------------------
export function Modal({ open, title, onClose, children, footer, size = 'md' }) {
  useEffect(() => {
    if (!open) return undefined
    function onKey(event) {
      if (event.key === 'Escape') onClose?.()
    }
    document.addEventListener('keydown', onKey)
    // Stop the page behind the dialog from scrolling while it is open.
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      document.removeEventListener('keydown', onKey)
      document.body.style.overflow = previousOverflow
    }
  }, [open, onClose])

  if (!open) return null

  const widths = { sm: 'max-w-md', md: 'max-w-lg', lg: 'max-w-2xl', xl: 'max-w-4xl' }

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-ink/40 p-4 backdrop-blur-sm sm:p-6">
      <button
        type="button"
        className="fixed inset-0 -z-10 cursor-default"
        onClick={onClose}
        tabIndex={-1}
        aria-hidden="true"
      />
      <div
        role="dialog"
        aria-modal="true"
        aria-label={title}
        className={`mt-4 w-full animate-scale-in overflow-hidden rounded-2xl bg-surface shadow-pop sm:mt-10 ${
          widths[size] ?? widths.md
        }`}
      >
        <div className="flex items-center justify-between gap-4 border-b border-hairline px-5 py-4 sm:px-6">
          <h2 className="text-base font-semibold tracking-tight text-ink">{title}</h2>
          <button type="button" onClick={onClose} className="btn-icon -mr-1" aria-label="Close">
            <CloseIcon className="h-4 w-4" />
          </button>
        </div>
        <div className="max-h-[70vh] overflow-y-auto px-5 py-5 sm:px-6">{children}</div>
        {footer && (
          <div className="flex flex-wrap justify-end gap-2 border-t border-hairline bg-slate-50/70 px-5 py-3.5 sm:px-6">
            {footer}
          </div>
        )}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Misc
// ---------------------------------------------------------------------------
export function ConfidenceMeter({ value, className = '' }) {
  if (value === null || value === undefined) return null
  const pct = Math.round(Number(value) * 100)
  const tone = pct >= 90 ? 'success' : pct >= 75 ? 'warning' : 'danger'
  return (
    <div className={className}>
      <div className="mb-1.5 flex items-center justify-between text-xs">
        <span className="font-medium text-ink-muted">Classifier confidence</span>
        <span className="font-semibold tabular-nums text-ink">{pct}%</span>
      </div>
      <div className="h-2 w-full overflow-hidden rounded-full bg-slate-200">
        <div
          className={`h-full rounded-full transition-[width] duration-500 ease-smooth ${
            tone === 'success' ? 'bg-emerald-500' : tone === 'warning' ? 'bg-amber-500' : 'bg-rose-500'
          }`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <p className="mt-1.5 text-[0.6875rem] text-ink-faint">
        {tone === 'success'
          ? 'High confidence — the category is almost certainly right.'
          : tone === 'warning'
            ? 'Moderate confidence — worth a quick check.'
            : 'Low confidence — an agent should verify the category.'}
      </p>
    </div>
  )
}

/** Build a compact page-number window around the current page. */
function pageWindow(current, total) {
  const pages = []
  const start = Math.max(1, Math.min(current - 1, total - 2))
  const end = Math.min(total, start + 2)
  for (let page = start; page <= end; page += 1) pages.push(page)
  return pages
}

export function Pagination({ pagination, onChange }) {
  if (!pagination || !pagination.total_pages || pagination.total_pages <= 1) return null
  const { page, total_pages, total } = pagination
  const pages = pageWindow(page, total_pages)

  return (
    <div className="flex flex-wrap items-center justify-between gap-3 border-t border-hairline px-4 py-3 sm:px-6">
      <p className="text-xs text-ink-muted">
        Page <span className="font-semibold tabular-nums text-ink">{page}</span> of {total_pages}
        <span className="mx-1.5 text-slate-300">|</span>
        <span className="tabular-nums">{total}</span> result{total === 1 ? '' : 's'}
      </p>

      <div className="flex items-center gap-1">
        <button
          type="button"
          className="btn-icon h-8 w-8"
          aria-label="Previous page"
          disabled={!pagination.has_prev && page <= 1}
          onClick={() => onChange(page - 1)}
        >
          <ChevronLeftIcon className="h-4 w-4" />
        </button>

        {pages.map((pageNumber) => (
          <button
            key={pageNumber}
            type="button"
            onClick={() => onChange(pageNumber)}
            aria-current={pageNumber === page ? 'page' : undefined}
            className={`h-8 min-w-8 rounded-lg px-2 text-xs font-semibold tabular-nums transition ${
              pageNumber === page
                ? 'bg-brand-600 text-white shadow-sm'
                : 'text-ink-soft hover:bg-slate-100 hover:text-ink'
            }`}
          >
            {pageNumber}
          </button>
        ))}

        <button
          type="button"
          className="btn-icon h-8 w-8"
          aria-label="Next page"
          disabled={!pagination.has_next || page >= total_pages}
          onClick={() => onChange(page + 1)}
        >
          <ChevronRightIcon className="h-4 w-4" />
        </button>
      </div>
    </div>
  )
}
