import { Link, useLocation } from 'react-router-dom'
import { useAuth } from '../context/AuthContext.jsx'
import { HOME_FOR_ROLE } from '../App.jsx'
import { ArrowLeftIcon, HelpCircleIcon, LogoMark } from '../components/icons.jsx'

export default function NotFound() {
  const { isAuthenticated, role } = useAuth()
  const location = useLocation()
  const home = isAuthenticated ? (HOME_FOR_ROLE[role] ?? '/dashboard') : '/login'

  return (
    <div className="auth-canvas">
      <div className="relative z-10 w-full max-w-lg text-center">
        <Link to="/" className="inline-flex">
          <LogoMark className="h-12 w-12" />
        </Link>

        <div className="card mt-6 p-8 shadow-card-xl sm:p-10">
          <span className="mx-auto flex h-16 w-16 items-center justify-center rounded-2xl bg-slate-100 text-slate-400 ring-1 ring-slate-200/70">
            <HelpCircleIcon className="h-8 w-8" />
          </span>

          <p className="mt-6 text-5xl font-semibold tracking-tight text-slate-200">404</p>
          <h1 className="mt-1 text-xl font-semibold tracking-tight text-ink">Page not found</h1>
          <p className="mx-auto mt-3 max-w-sm text-sm leading-relaxed text-ink-muted">
            Nothing is routed at this address. It may have been moved, or the link may be out of
            date.
          </p>

          <code className="mt-4 inline-block max-w-full break-all rounded-lg bg-slate-100 px-3 py-1.5 font-mono text-xs text-ink-soft">
            {location.pathname}
          </code>

          <div className="mt-7">
            <Link to={home} className="btn-primary">
              <ArrowLeftIcon className="h-4 w-4" />
              {isAuthenticated ? 'Back to my dashboard' : 'Go to sign in'}
            </Link>
          </div>
        </div>
      </div>
    </div>
  )
}
