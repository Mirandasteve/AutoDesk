import { Link, NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { useEffect, useState } from 'react'
import { useAuth } from '../context/AuthContext.jsx'
import { Alert } from './ui.jsx'
import {
  BellIcon,
  ChartIcon,
  CloseIcon,
  CpuIcon,
  GaugeIcon,
  HandIcon,
  HomeIcon,
  InboxIcon,
  LogoMark,
  LogOutIcon,
  MenuIcon,
  PlusIcon,
  TicketIcon,
  UsersIcon,
} from './icons.jsx'
import { notificationApi } from '../services/api'
import { initials } from '../utils/format.jsx'

/**
 * Navigation model.
 *
 * Declared once per role so the sidebar, the mobile drawer and the page
 * breadcrumbs all read from the same source of truth.
 */
const NAV_SECTIONS = [
  {
    id: 'workspace',
    label: 'Workspace',
    roles: ['employee'],
    items: [
      { to: '/dashboard', label: 'Dashboard', icon: HomeIcon, end: true },
      { to: '/tickets/new', label: 'Raise a ticket', icon: PlusIcon },
      { to: '/tickets/my', label: 'My tickets', icon: TicketIcon },
    ],
  },
  {
    id: 'support',
    label: 'Support desk',
    roles: ['agent', 'admin'],
    items: [
      { to: '/agent', label: 'Team dashboard', icon: GaugeIcon, end: true },
      { to: '/agent/tickets', label: 'Team queue', icon: InboxIcon },
      { to: '/agent/my-tickets', label: 'My assignments', icon: HandIcon },
    ],
  },
  {
    id: 'admin',
    label: 'Administration',
    roles: ['admin'],
    items: [
      { to: '/admin', label: 'Overview', icon: ChartIcon, end: true },
      { to: '/admin/tickets', label: 'All tickets', icon: TicketIcon },
      { to: '/admin/analytics', label: 'Analytics', icon: ChartIcon },
      { to: '/admin/users', label: 'Users', icon: UsersIcon },
      { to: '/admin/ml', label: 'ML status', icon: CpuIcon },
    ],
  },
]

const PORTAL_LABEL = {
  employee: 'Employee portal',
  agent: 'Support desk',
  admin: 'Administrator',
}

const ROLE_BADGE = {
  employee: 'badge-role-employee',
  agent: 'badge-role-agent',
  admin: 'badge-role-admin',
}

/** One navigation entry. Active entries get a tinted background and a rail. */
function NavItem({ item, onNavigate, badge }) {
  const Icon = item.icon
  return (
    <NavLink
      to={item.to}
      end={item.end}
      onClick={onNavigate}
      className={({ isActive }) =>
        `group relative flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition duration-150 ease-smooth ${
          isActive
            ? 'bg-brand-50 text-brand-700'
            : 'text-ink-soft hover:bg-slate-100 hover:text-ink'
        }`
      }
    >
      {({ isActive }) => (
        <>
          <span
            aria-hidden="true"
            className={`absolute left-0 top-1/2 h-5 w-1 -translate-y-1/2 rounded-r-full bg-brand-600 transition-opacity ${
              isActive ? 'opacity-100' : 'opacity-0'
            }`}
          />
          <Icon
            className={`h-[18px] w-[18px] shrink-0 transition-colors ${
              isActive ? 'text-brand-600' : 'text-slate-400 group-hover:text-slate-600'
            }`}
          />
          <span className="min-w-0 flex-1 truncate">{item.label}</span>
          {badge > 0 && (
            <span className="inline-flex h-5 min-w-5 items-center justify-center rounded-full bg-brand-600 px-1.5 text-[0.625rem] font-bold tabular-nums text-white">
              {badge > 99 ? '99+' : badge}
            </span>
          )}
        </>
      )}
    </NavLink>
  )
}

function SidebarContent({ role, user, unread, onNavigate, onLogout }) {
  const sections = NAV_SECTIONS.filter((section) => section.roles.includes(role))

  return (
    <div className="flex h-full flex-col">
      <Link
        to="/"
        onClick={onNavigate}
        className="flex items-center gap-3 px-4 pb-5 pt-6"
      >
        <LogoMark className="h-10 w-10" />
        <div className="min-w-0">
          <p className="text-[0.9375rem] font-semibold leading-tight tracking-tight text-ink">
            AutoDesk
          </p>
          <p className="truncate text-xs text-ink-muted">{PORTAL_LABEL[role] ?? 'IT Support Portal'}</p>
        </div>
      </Link>

      <nav className="flex-1 space-y-6 overflow-y-auto px-3 pb-4">
        {sections.map((section) => (
          <div key={section.id}>
            <p className="px-3 pb-2 text-[0.6875rem] font-semibold uppercase tracking-[0.09em] text-ink-faint">
              {section.label}
            </p>
            <div className="space-y-0.5">
              {section.items.map((item) => (
                <NavItem key={item.to} item={item} onNavigate={onNavigate} />
              ))}
            </div>
          </div>
        ))}

        <div>
          <p className="px-3 pb-2 text-[0.6875rem] font-semibold uppercase tracking-[0.09em] text-ink-faint">
            Account
          </p>
          <div className="space-y-0.5">
            <NavItem
              item={{ to: '/notifications', label: 'Notifications', icon: BellIcon }}
              onNavigate={onNavigate}
              badge={unread}
            />
          </div>
        </div>
      </nav>

      <div className="border-t border-hairline p-3">
        <div className="rounded-xl bg-slate-50 p-3">
          <div className="flex items-center gap-3">
            <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-brand-gradient text-xs font-bold text-white">
              {initials(user?.name)}
            </span>
            <div className="min-w-0 flex-1">
              <p className="truncate text-[0.8125rem] font-semibold text-ink">{user?.name}</p>
              <p className="truncate text-xs text-ink-muted">{user?.email}</p>
            </div>
          </div>

          <div className="mt-3 flex flex-wrap items-center gap-1.5">
            <span className={`badge badge-soft ${ROLE_BADGE[user?.role] ?? 'badge-role-employee'}`}>
              {user?.role}
            </span>
            {user?.team && <span className="chip">{user.team}</span>}
          </div>

          <button type="button" onClick={onLogout} className="btn-secondary btn-sm mt-3 w-full">
            <LogOutIcon className="h-4 w-4" />
            Sign out
          </button>
        </div>
      </div>
    </div>
  )
}

export default function AppShell() {
  const { user, logout, role, sessionNotice, dismissNotice } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const [unread, setUnread] = useState(0)
  const [drawerOpen, setDrawerOpen] = useState(false)

  useEffect(() => {
    let cancelled = false
    async function loadUnread() {
      try {
        const data = await notificationApi.unreadCount()
        if (!cancelled) setUnread(data.unread_count ?? data.count ?? 0)
      } catch {
        // The notification centre is not the only thing the UI needs. Fail
        // quietly so it never blocks the portal.
      }
    }
    loadUnread()
    return () => {
      cancelled = true
    }
  }, [])

  // Navigating with the drawer open should always reveal the new page.
  useEffect(() => {
    setDrawerOpen(false)
  }, [location.pathname])

  useEffect(() => {
    document.body.style.overflow = drawerOpen ? 'hidden' : ''
    return () => {
      document.body.style.overflow = ''
    }
  }, [drawerOpen])

  function onLogout() {
    logout()
    navigate('/login', { replace: true })
  }

  const current = NAV_SECTIONS.flatMap((section) => section.items).find(
    (item) =>
      item.to === location.pathname ||
      (item.to !== '/dashboard' && item.to !== '/agent' && item.to !== '/admin'
        ? location.pathname.startsWith(item.to)
        : false),
  )

  return (
    <div className="flex min-h-screen bg-canvas bg-canvas-mesh">
      {/* ---- Desktop sidebar ---- */}
      <aside className="sticky top-0 hidden h-screen w-[17rem] shrink-0 border-r border-hairline bg-surface shadow-nav lg:flex">
        <SidebarContent
          role={role}
          user={user}
          unread={unread}
          onLogout={onLogout}
        />
      </aside>

      {/* ---- Mobile drawer ---- */}
      {drawerOpen && (
        <div className="fixed inset-0 z-50 lg:hidden">
          <button
            type="button"
            className="absolute inset-0 animate-fade-in bg-ink/40 backdrop-blur-sm"
            onClick={() => setDrawerOpen(false)}
            aria-label="Close navigation"
          />
          <aside className="relative flex h-full w-[17rem] max-w-[85vw] animate-slide-in-left flex-col border-r border-hairline bg-surface shadow-pop">
            <button
              type="button"
              onClick={() => setDrawerOpen(false)}
              className="btn-icon absolute right-2 top-4 z-10"
              aria-label="Close navigation"
            >
              <CloseIcon className="h-4 w-4" />
            </button>
            <SidebarContent
              role={role}
              user={user}
              unread={unread}
              onNavigate={() => setDrawerOpen(false)}
              onLogout={onLogout}
            />
          </aside>
        </div>
      )}

      <div className="flex min-w-0 flex-1 flex-col">
        {/* ---- Mobile top bar ---- */}
        <div className="sticky top-0 z-40 flex items-center justify-between gap-3 border-b border-hairline bg-surface/90 px-4 py-3 backdrop-blur lg:hidden">
          <button
            type="button"
            onClick={() => setDrawerOpen(true)}
            className="btn-icon -ml-1 border border-slate-200"
            aria-label="Open navigation"
          >
            <MenuIcon className="h-5 w-5" />
          </button>
          <div className="flex min-w-0 items-center gap-2.5">
            <LogoMark className="h-8 w-8" />
            <span className="truncate text-sm font-semibold tracking-tight text-ink">AutoDesk</span>
          </div>
          <Link to="/notifications" className="btn-icon relative -mr-1" aria-label="Notifications">
            <BellIcon className="h-5 w-5" />
            {unread > 0 && (
              <span className="absolute right-1 top-1 h-2 w-2 rounded-full bg-rose-500 ring-2 ring-surface" />
            )}
          </Link>
        </div>

        {/* ---- Desktop header ---- */}
        <header
          data-app-header="true"
          className="sticky top-0 z-30 hidden items-center justify-between gap-4 border-b border-hairline bg-surface/85 px-8 py-3.5 backdrop-blur lg:flex"
        >
          <div className="min-w-0">
            <nav aria-label="Breadcrumb" className="flex items-center gap-2 text-xs text-ink-faint">
              <span className="font-medium">{PORTAL_LABEL[role] ?? 'AutoDesk'}</span>
              {current && (
                <>
                  <span aria-hidden="true">/</span>
                  <span className="font-semibold text-ink-soft">{current.label}</span>
                </>
              )}
            </nav>
            <p className="mt-0.5 truncate text-sm font-semibold tracking-tight text-ink">
              {current?.label ?? 'AutoDesk'}
            </p>
          </div>

          <div className="flex shrink-0 items-center gap-2">
            <Link
              to="/notifications"
              className="btn-icon relative border border-slate-200"
              aria-label={`Notifications${unread > 0 ? `, ${unread} unread` : ''}`}
            >
              <BellIcon className="h-5 w-5" />
              {unread > 0 && (
                <span className="absolute -right-1.5 -top-1.5 inline-flex h-5 min-w-5 items-center justify-center rounded-full bg-rose-500 px-1 text-[0.625rem] font-bold tabular-nums text-white ring-2 ring-surface">
                  {unread > 99 ? '99+' : unread}
                </span>
              )}
            </Link>
            <span className={`badge badge-soft ${ROLE_BADGE[role] ?? 'badge-role-employee'}`}>
              {role}
            </span>
          </div>
        </header>

        {/* ---- Page content ---- */}
        <main className="flex-1 px-4 py-6 sm:px-6 lg:px-8 lg:py-8">
          <div className="mx-auto w-full max-w-[86rem]">
            {sessionNotice && (
              <div className="mb-5">
                <Alert tone="warning" title="Session changed" onDismiss={dismissNotice}>
                  {sessionNotice}
                </Alert>
              </div>
            )}
            <Outlet />
          </div>
        </main>

        <footer className="border-t border-hairline bg-surface/70 px-4 py-4 text-center text-xs text-ink-faint sm:px-6 lg:px-8">
          AutoDesk &mdash; a machine-learning based IT ticket classification and routing system
        </footer>
      </div>
    </div>
  )
}
