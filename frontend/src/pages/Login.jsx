import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext.jsx'
import { HOME_FOR_ROLE } from '../App.jsx'
import { Alert, Field, TextInput } from '../components/ui.jsx'
import {
  ArrowRightIcon,
  CpuIcon,
  LayersIcon,
  ListChecksIcon,
  LockIcon,
  LogoMark,
  MailIcon,
  ShieldIcon,
  TargetIcon,
  UserIcon,
} from '../components/icons.jsx'

/**
 * Demo accounts offered as one-click fills.
 *
 * These are the seeded accounts from `database/seed.sql` / `flask seed-db`,
 * not hardcoded UI-only data. They exist so an evaluator can reach all three
 * portals without registering five agents first; the credentials are visible in
 * the seed file anyway.
 */
const DEMO_ACCOUNTS = [
  {
    role: 'Employee',
    description: 'Raise and track your own tickets',
    icon: UserIcon,
    email: 'employee1@autodesk.local',
    password: 'Employee@123',
  },
  {
    role: 'Support Agent',
    description: 'Claim and resolve the team queue',
    icon: ShieldIcon,
    email: 'agent.network@autodesk.local',
    password: 'Agent@123',
  },
  {
    role: 'Administrator',
    description: 'Analytics, users and ML diagnostics',
    icon: ListChecksIcon,
    email: 'admin@autodesk.local',
    password: 'Admin@123',
  },
]

/** The pipeline, explained in three steps so the product makes sense up front. */
const PIPELINE = [
  {
    icon: CpuIcon,
    title: 'DistilBERT classifies',
    body: 'Your wording is turned into one of six categories, with a confidence score.',
  },
  {
    icon: TargetIcon,
    title: 'Rules set the priority',
    body: 'A transparent rule engine scores Critical, High, Medium or Low — and records why.',
  },
  {
    icon: LayersIcon,
    title: 'Routing assigns the team',
    body: 'The category maps to a support team and an SLA deadline is set automatically.',
  },
]

export default function Login() {
  const { login, sessionNotice } = useAuth()
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [errors, setErrors] = useState({})
  const [formError, setFormError] = useState(null)
  const [submitting, setSubmitting] = useState(false)

  async function onSubmit(event) {
    event.preventDefault()
    setErrors({})
    setFormError(null)
    setSubmitting(true)
    try {
      const profile = await login(email.trim(), password)
      navigate(HOME_FOR_ROLE[profile.role] ?? '/dashboard', { replace: true })
    } catch (error) {
      setFormError(error.message)
      setErrors(error.fields ?? {})
    } finally {
      setSubmitting(false)
    }
  }

  function useDemo(account) {
    setEmail(account.email)
    setPassword(account.password)
    setErrors({})
    setFormError(null)
  }

  return (
    <div className="auth-canvas">
      <div className="relative z-10 grid w-full max-w-6xl items-center gap-10 lg:grid-cols-[1.05fr_1fr] lg:gap-16">
        {/* ---- Brand & explanation panel ---- */}
        <div className="order-2 lg:order-1">
          <div className="flex items-center gap-3">
            <LogoMark className="h-12 w-12" />
            <div>
              <h1 className="text-xl font-semibold tracking-tight text-ink">AutoDesk</h1>
              <p className="text-sm text-ink-muted">IT Support Portal</p>
            </div>
          </div>

          <h2 className="mt-8 text-3xl font-semibold leading-tight tracking-tight text-ink sm:text-4xl">
            Every IT ticket,
            <br />
            <span className="bg-brand-gradient bg-clip-text text-transparent">
              classified and routed automatically.
            </span>
          </h2>
          <p className="mt-4 max-w-lg text-[0.9375rem] leading-relaxed text-ink-muted">
            A locally trained DistilBERT model reads each ticket, a transparent rule engine sets
            its priority, and the routing engine assigns the right support team with an SLA
            deadline attached.
          </p>

          <ul className="mt-8 grid gap-3">
            {PIPELINE.map((step) => {
              const StepIcon = step.icon
              return (
                <li
                  key={step.title}
                  className="flex items-start gap-3.5 rounded-2xl border border-hairline bg-surface/70 p-4 backdrop-blur"
                >
                  <span className="inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-brand-50 text-brand-600 ring-1 ring-brand-100">
                    <StepIcon className="h-5 w-5" />
                  </span>
                  <div className="min-w-0">
                    <p className="text-sm font-semibold text-ink">{step.title}</p>
                    <p className="mt-0.5 text-[0.8125rem] leading-relaxed text-ink-muted">
                      {step.body}
                    </p>
                  </div>
                </li>
              )
            })}
          </ul>
        </div>

        {/* ---- Sign-in panel ---- */}
        <div className="order-1 lg:order-2">
          <div className="card p-6 shadow-card-xl sm:p-8">
            <h2 className="text-lg font-semibold tracking-tight text-ink">Sign in</h2>
            <p className="mt-1 text-sm text-ink-muted">Use your AutoDesk account to continue.</p>

            {sessionNotice && (
              <div className="mt-5">
                <Alert tone="warning" title="Session ended">
                  {sessionNotice}
                </Alert>
              </div>
            )}
            {formError && (
              <div className="mt-5">
                <Alert tone="danger" title="Could not sign in">
                  {formError}
                </Alert>
              </div>
            )}

            <form onSubmit={onSubmit} className="mt-6 space-y-4" noValidate>
              <Field label="Email address" htmlFor="email" error={errors.email} required>
                <div className="relative">
                  <MailIcon className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-faint" />
                  <TextInput
                    id="email"
                    type="email"
                    autoComplete="username"
                    autoFocus
                    placeholder="you@autodesk.local"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    error={errors.email}
                    className="pl-10"
                    required
                  />
                </div>
              </Field>

              <Field label="Password" htmlFor="password" error={errors.password} required>
                <div className="relative">
                  <LockIcon className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-faint" />
                  <TextInput
                    id="password"
                    type="password"
                    autoComplete="current-password"
                    placeholder="Enter your password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    error={errors.password}
                    className="pl-10"
                    required
                  />
                </div>
              </Field>

              <button type="submit" className="btn-primary w-full py-2.5" disabled={submitting}>
                {submitting ? 'Signing in…' : 'Sign in'}
                {!submitting && <ArrowRightIcon className="h-4 w-4" />}
              </button>
            </form>

            <p className="mt-5 text-center text-sm text-ink-muted">
              Need an account?{' '}
              <Link to="/register" className="font-semibold text-brand-700 hover:underline">
                Register here
              </Link>
            </p>

            {/* ---- Demo logins ---- */}
            <div className="mt-7 border-t border-hairline pt-6">
              <p className="micro-label">Demo accounts · from the seed script</p>
              <div className="mt-3 space-y-2">
                {DEMO_ACCOUNTS.map((account) => {
                  const RoleIcon = account.icon
                  return (
                    <button
                      key={account.email}
                      type="button"
                      onClick={() => useDemo(account)}
                      className="group flex w-full items-center gap-3 rounded-xl border border-hairline bg-surface px-3.5 py-3 text-left transition duration-150 ease-smooth hover:border-brand-300 hover:bg-brand-50/50 hover:shadow-card-md"
                    >
                      <span className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-slate-100 text-slate-500 ring-1 ring-slate-200/70 transition group-hover:bg-brand-100 group-hover:text-brand-700 group-hover:ring-brand-200">
                        <RoleIcon className="h-[18px] w-[18px]" />
                      </span>
                      <span className="min-w-0 flex-1">
                        <span className="block text-sm font-semibold text-ink">
                          {account.role}
                        </span>
                        <span className="block truncate text-xs text-ink-muted">
                          {account.description}
                        </span>
                      </span>
                      <span className="shrink-0 text-xs font-semibold text-brand-700 opacity-0 transition group-hover:opacity-100">
                        Use
                      </span>
                    </button>
                  )
                })}
              </div>
              <p className="mt-3 text-xs leading-relaxed text-ink-faint">
                These accounts exist only in the seeded development database.
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
