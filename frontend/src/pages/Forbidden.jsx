import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext.jsx'
import { HOME_FOR_ROLE } from '../App.jsx'
import { HomeIcon, LogoMark, LogOutIcon, ShieldIcon } from '../components/icons.jsx'

/**
 * Shown when a signed-in user opens a portal they do not have access to.
 *
 * The server enforces roles independently, so this screen exists purely to
 * explain the redirect rather than to act as a security control.
 */
export default function Forbidden() {
  const { role } = useAuth()
  const navigate = useNavigate()
  const home = HOME_FOR_ROLE[role] ?? '/dashboard'

  return (
    <div className="auth-canvas">
      <div className="relative z-10 w-full max-w-lg text-center">
        <Link to="/" className="inline-flex">
          <LogoMark className="h-12 w-12" />
        </Link>

        <div className="card mt-6 p-8 shadow-card-xl sm:p-10">
          <span className="mx-auto flex h-16 w-16 items-center justify-center rounded-2xl bg-rose-50 text-rose-500 ring-1 ring-rose-100">
            <ShieldIcon className="h-8 w-8" />
          </span>

          <p className="mt-6 text-5xl font-semibold tracking-tight text-slate-200">403</p>
          <h1 className="mt-1 text-xl font-semibold tracking-tight text-ink">Access denied</h1>
          <p className="mx-auto mt-3 max-w-sm text-sm leading-relaxed text-ink-muted">
            Your account does not have permission to view that page. If you believe this is a
            mistake, ask an administrator to review your role and support team.
          </p>

          <div className="mt-5 inline-flex items-center gap-2 rounded-full bg-slate-100 px-3 py-1.5">
            <span className="text-[0.6875rem] font-semibold uppercase tracking-[0.08em] text-ink-faint">
              Signed in as
            </span>
            <span className="badge badge-soft badge-role-employee">{role ?? 'unknown role'}</span>
          </div>

          <div className="mt-7 flex flex-wrap justify-center gap-2">
            <button
              type="button"
              className="btn-primary"
              onClick={() => navigate(home, { replace: true })}
            >
              <HomeIcon className="h-4 w-4" />
              Go to my dashboard
            </button>
            <Link to="/login" className="btn-secondary">
              <LogOutIcon className="h-4 w-4" />
              Sign in as someone else
            </Link>
          </div>
        </div>
      </div>
    </div>
  )
}
