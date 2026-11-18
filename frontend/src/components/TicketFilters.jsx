/**
 * Shared filter bar for every ticket list screen.
 *
 * The dropdowns read their options from `useMeta()`, which the backend feeds
 * from `/api/meta`, so the UI can never offer a status, priority or category the
 * API would reject. `fields` declares which filters this particular list needs.
 */
import { useMeta } from '../context/MetaContext.jsx'
import { SearchInput, Select } from './ui.jsx'
import { FilterIcon } from './icons.jsx'

const FALLBACK = {
  statuses: ['Open', 'In Progress', 'Resolved'],
  priorities: ['Critical', 'High', 'Medium', 'Low'],
  categories: ['Software', 'Hardware', 'Network', 'Login', 'VPN', 'Access'],
}

const LABELS = {
  status: 'Status',
  priority: 'Priority',
  category: 'Category',
  team: 'Team',
  assigned: 'Assignment',
}

const PLACEHOLDERS = {
  status: 'All statuses',
  priority: 'All priorities',
  category: 'All categories',
  team: 'All teams',
  assigned: 'Anyone',
}

function labelled(label, control) {
  return (
    <label className="block">
      <span className="label">{label}</span>
      {control}
    </label>
  )
}

export default function TicketFilters({
  value,
  onChange,
  onReset,
  searchPlaceholder = 'Search titles…',
  fields = ['status', 'priority', 'category'],
  teams = [],
  children,
}) {
  const meta = useMeta()
  const statuses = meta.statuses.length ? meta.statuses : FALLBACK.statuses
  const priorities = meta.priorities.length ? meta.priorities : FALLBACK.priorities
  const categories = meta.categories.length ? meta.categories : FALLBACK.categories

  const active = fields.some((field) => value[field]) || value.search
  const columnClass =
    fields.length >= 5
      ? 'grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5'
      : fields.length === 4
        ? 'grid gap-4 sm:grid-cols-2 lg:grid-cols-4'
        : 'grid gap-4 sm:grid-cols-3'

  return (
    <div className="card mb-6 p-4 sm:p-5">
      <div className="mb-4 flex items-center justify-between gap-3">
        <p className="flex items-center gap-2 text-[0.8125rem] font-semibold text-ink">
          <FilterIcon className="h-4 w-4 text-ink-muted" />
          Filters
        </p>
        {active && onReset && (
          <button type="button" onClick={onReset} className="btn-ghost btn-sm">
            Clear all
          </button>
        )}
      </div>

      <div className={columnClass}>
        <label className="block">
          <span className="label">Search</span>
          <SearchInput
            aria-label="Search tickets"
            placeholder={searchPlaceholder}
            value={value.search ?? ''}
            onChange={(event) => onChange('search', event.target.value)}
          />
        </label>

        {fields.includes('status') &&
          labelled(
            LABELS.status,
            <Select
              aria-label="Filter by status"
              value={value.status ?? ''}
              onChange={(event) => onChange('status', event.target.value)}
            >
              <option value="">{PLACEHOLDERS.status}</option>
              {statuses.map((status) => (
                <option key={status} value={status}>
                  {status}
                </option>
              ))}
            </Select>,
          )}

        {fields.includes('priority') &&
          labelled(
            LABELS.priority,
            <Select
              aria-label="Filter by priority"
              value={value.priority ?? ''}
              onChange={(event) => onChange('priority', event.target.value)}
            >
              <option value="">{PLACEHOLDERS.priority}</option>
              {priorities.map((priority) => (
                <option key={priority} value={priority}>
                  {priority}
                </option>
              ))}
            </Select>,
          )}

        {fields.includes('category') &&
          labelled(
            LABELS.category,
            <Select
              aria-label="Filter by category"
              value={value.category ?? ''}
              onChange={(event) => onChange('category', event.target.value)}
            >
              <option value="">{PLACEHOLDERS.category}</option>
              {categories.map((category) => (
                <option key={category} value={category}>
                  {category}
                </option>
              ))}
            </Select>,
          )}

        {fields.includes('team') &&
          labelled(
            LABELS.team,
            <Select
              aria-label="Filter by team"
              value={value.team ?? ''}
              onChange={(event) => onChange('team', event.target.value)}
            >
              <option value="">{PLACEHOLDERS.team}</option>
              {teams.map((team) => (
                <option key={team} value={team}>
                  {team}
                </option>
              ))}
            </Select>,
          )}

        {fields.includes('assigned') &&
          labelled(
            LABELS.assigned,
            <Select
              aria-label="Filter by assignment"
              value={value.assigned ?? ''}
              onChange={(event) => onChange('assigned', event.target.value)}
            >
              <option value="">{PLACEHOLDERS.assigned}</option>
              <option value="me">Assigned to me</option>
              <option value="unassigned">Unassigned</option>
            </Select>,
          )}

        {children}
      </div>
    </div>
  )
}
