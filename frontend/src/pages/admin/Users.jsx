import { useEffect, useState } from 'react'
import { useAsync, useDebounced } from '../../hooks/useAsync.js'
import { adminApi } from '../../services/api'
import { formatDate, initials, toQuery } from '../../utils/format.jsx'
import {
  Alert,
  Card,
  DataTable,
  EmptyState,
  ErrorState,
  Field,
  Modal,
  PageHeader,
  Pagination,
  Select,
  SkeletonTable,
} from '../../components/ui.jsx'
import { EditIcon, SearchIcon, UserIcon, UsersIcon } from '../../components/icons.jsx'

const ROLE_BADGES = {
  employee: 'badge-role-employee',
  agent: 'badge-role-agent',
  admin: 'badge-role-admin',
}

const EMPTY_FILTERS = { role: '', team: '', search: '' }

/**
 * User management (SRS section 51).
 *
 * Two server-side guards are surfaced rather than re-implemented here:
 *   * an admin cannot change their own role or deactivate themselves,
 *   * the last active administrator cannot be demoted.
 * Both return 403, which is rendered as a plain explanation. The own-row
 * controls are additionally disabled so the mistake is not easy to make.
 */
export default function Users() {
  const [filters, setFilters] = useState(EMPTY_FILTERS)
  const [page, setPage] = useState(1)
  const [editing, setEditing] = useState(null)
  const [form, setForm] = useState({ name: '', role: '', team: '', is_active: true })
  const [notice, setNotice] = useState(null)
  const [actionError, setActionError] = useState(null)
  const [busy, setBusy] = useState(false)
  const debouncedSearch = useDebounced(filters.search, 400)

  const { data, loading, error, reload } = useAsync(
    () => adminApi.users(toQuery({ ...filters, search: debouncedSearch, page, page_size: 15 })),
    [filters.role, filters.team, debouncedSearch, page],
  )

  const roles = data?.roles ?? ['employee', 'agent', 'admin']
  const teams = data?.teams ?? []

  function update(key, value) {
    setFilters((current) => ({ ...current, [key]: value }))
    setPage(1)
  }

  function reset() {
    setFilters(EMPTY_FILTERS)
    setPage(1)
  }

  function openEditor(user) {
    setEditing(user)
    setActionError(null)
    setForm({
      name: user.name ?? '',
      role: user.role,
      team: user.team ?? '',
      is_active: user.is_active,
    })
  }

  // Keep the team selector honest: a non-agent has no support team.
  useEffect(() => {
    if (form.role !== 'agent') setForm((current) => ({ ...current, team: '' }))
  }, [form.role])

  async function save(event) {
    event.preventDefault()
    setBusy(true)
    setActionError(null)
    try {
      const payload = { name: form.name.trim(), role: form.role, is_active: form.is_active }
      // Sending the key only when the admin changed it avoids clearing the team
      // on an unrelated edit.
      if (form.role === 'agent' && form.team) payload.team = form.team
      const result = await adminApi.updateUser(editing.id, payload)
      setNotice(result.message ?? 'User updated.')
      setEditing(null)
      await reload()
    } catch (err) {
      setActionError(err.message)
    } finally {
      setBusy(false)
    }
  }

  const users = data?.items ?? []

  return (
    <>
      <PageHeader
        eyebrow="Administration"
        title="User management"
        description="Change a user's role, support team or active status."
      />

      {notice && (
        <div className="mb-5">
          <Alert tone="success" onDismiss={() => setNotice(null)}>
            {notice}
          </Alert>
        </div>
      )}

      <div className="card mb-6 p-4 sm:p-5">
        <div className="mb-4 flex items-center justify-between gap-3">
          <p className="flex items-center gap-2 text-[0.8125rem] font-semibold text-ink">
            <SearchIcon className="h-4 w-4 text-ink-muted" />
            Filters
          </p>
          {(filters.role || filters.team || filters.search) && (
            <button type="button" onClick={reset} className="btn-ghost btn-sm">
              Clear all
            </button>
          )}
        </div>

        <div className="grid gap-4 sm:grid-cols-3">
          <label className="block">
            <span className="label">Search</span>
            <div className="relative">
              <SearchIcon className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-faint" />
              <input
                className="input pl-10"
                aria-label="Search users"
                placeholder="Name or email…"
                value={filters.search}
                onChange={(e) => update('search', e.target.value)}
              />
            </div>
          </label>

          <label className="block">
            <span className="label">Role</span>
            <Select
              aria-label="Filter by role"
              value={filters.role}
              onChange={(e) => update('role', e.target.value)}
            >
              <option value="">All roles</option>
              {roles.map((role) => (
                <option key={role} value={role}>
                  {role}
                </option>
              ))}
            </Select>
          </label>

          <label className="block">
            <span className="label">Team</span>
            <Select
              aria-label="Filter by team"
              value={filters.team}
              onChange={(e) => update('team', e.target.value)}
            >
              <option value="">All teams</option>
              {teams.map((team) => (
                <option key={team} value={team}>
                  {team}
                </option>
              ))}
            </Select>
          </label>
        </div>
      </div>

      {loading && (
        <div className="card">
          <SkeletonTable rows={7} cols={5} />
        </div>
      )}
      {error && <ErrorState error={error} onRetry={reload} />}

      {!loading && !error && (
        <Card bodyClass="p-0">
          <DataTable
            columns={[
              {
                key: 'name',
                header: 'User',
                render: (u) => (
                  <div className="flex items-center gap-3">
                    <span className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-brand-100 text-xs font-bold text-brand-700">
                      {initials(u.name)}
                    </span>
                    <div className="min-w-0">
                      <p className="truncate font-semibold text-ink">
                        {u.name}
                        {u.is_self && (
                          <span className="ml-1.5 text-xs font-normal text-ink-faint">(you)</span>
                        )}
                      </p>
                      <p className="truncate text-xs text-ink-muted">{u.email}</p>
                    </div>
                  </div>
                ),
              },
              {
                key: 'role',
                header: 'Role',
                render: (u) => (
                  <span className={`badge badge-soft ${ROLE_BADGES[u.role] ?? 'badge-role-employee'}`}>
                    {u.role}
                  </span>
                ),
              },
              { key: 'team', header: 'Team', render: (u) => u.team ?? '—' },
              {
                key: 'tickets',
                header: 'Tickets',
                cellClassName: 'num',
                render: (u) => u.ticket_count ?? 0,
              },
              {
                key: 'active',
                header: 'Status',
                render: (u) => (
                  <span className={`badge badge-soft ${u.is_active ? 'badge-resolved' : 'badge-breached'}`}>
                    {u.is_active ? 'Active' : 'Disabled'}
                  </span>
                ),
              },
              {
                key: 'created_at',
                header: 'Joined',
                cellClassName: 'whitespace-nowrap text-ink-muted',
                render: (u) => formatDate(u.created_at),
              },
              {
                key: 'actions',
                header: '',
                cellClassName: 'text-right',
                render: (u) => (
                  <button
                    type="button"
                    className="btn-secondary btn-xs"
                    onClick={(event) => {
                      event.stopPropagation()
                      openEditor(u)
                    }}
                  >
                    <EditIcon className="h-3.5 w-3.5" />
                    Edit
                  </button>
                ),
              },
            ]}
            rows={users}
            empty={
              <EmptyState
                icon={UsersIcon}
                title="No users match"
                description="Adjust the filters above to widen the search."
              />
            }
          />
          <Pagination pagination={data?.pagination} onChange={setPage} />
        </Card>
      )}

      <Modal
        open={Boolean(editing)}
        title={editing ? `Edit ${editing.name}` : ''}
        onClose={() => setEditing(null)}
        footer={
          <>
            <button type="button" className="btn-secondary" onClick={() => setEditing(null)}>
              Cancel
            </button>
            <button type="submit" form="user-form" className="btn-primary" disabled={busy}>
              {busy ? 'Saving…' : 'Save changes'}
            </button>
          </>
        }
      >
        <form id="user-form" onSubmit={save} className="space-y-4">
          {actionError && (
            <Alert tone="danger" title="Could not update this user">
              {actionError}
            </Alert>
          )}

          {editing && (
            <div className="flex items-center gap-3 rounded-xl bg-slate-50 p-3.5">
              <span className="inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-brand-100 text-sm font-bold text-brand-700">
                {initials(editing.name)}
              </span>
              <div className="min-w-0">
                <p className="truncate text-sm font-semibold text-ink">{editing.email}</p>
                <p className="text-xs text-ink-muted">
                  {editing.ticket_count ?? 0} ticket{(editing.ticket_count ?? 0) === 1 ? '' : 's'} raised
                </p>
              </div>
            </div>
          )}

          <Field label="Name" htmlFor="user-name">
            <input
              id="user-name"
              className="input"
              value={form.name}
              onChange={(e) => setForm((current) => ({ ...current, name: e.target.value }))}
              required
            />
          </Field>

          <Field
            label="Role"
            htmlFor="user-role"
            hint={editing?.is_self ? 'You cannot change your own role.' : undefined}
          >
            <Select
              id="user-role"
              value={form.role}
              disabled={editing?.is_self}
              onChange={(e) => setForm((current) => ({ ...current, role: e.target.value }))}
            >
              {roles.map((role) => (
                <option key={role} value={role}>
                  {role}
                </option>
              ))}
            </Select>
          </Field>

          {form.role === 'agent' && (
            <Field
              label="Support team"
              htmlFor="user-team"
              hint="Determines which queue the agent sees."
            >
              <Select
                id="user-team"
                value={form.team}
                onChange={(e) => setForm((current) => ({ ...current, team: e.target.value }))}
              >
                <option value="">No team assigned</option>
                {teams.map((team) => (
                  <option key={team} value={team}>
                    {team}
                  </option>
                ))}
              </Select>
            </Field>
          )}

          <label className="flex items-start gap-3 rounded-xl border border-hairline bg-slate-50/60 p-3.5 transition hover:border-slate-300">
            <input
              type="checkbox"
              className="checkbox"
              checked={form.is_active}
              disabled={editing?.is_self}
              onChange={(e) => setForm((current) => ({ ...current, is_active: e.target.checked }))}
            />
            <span>
              <span className="flex items-center gap-1.5 text-sm font-semibold text-ink">
                <UserIcon className="h-4 w-4 text-ink-muted" />
                Account is active
              </span>
              <span className="mt-0.5 block text-xs leading-relaxed text-ink-muted">
                Disabled accounts cannot sign in.
                {editing?.is_self && ' You cannot disable your own account.'}
              </span>
            </span>
          </label>
        </form>
      </Modal>
    </>
  )
}
