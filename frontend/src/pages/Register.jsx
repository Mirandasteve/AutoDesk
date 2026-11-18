import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext.jsx'
import { authApi } from '../services/api'
import { HOME_FOR_ROLE } from '../App.jsx'
import { Alert, Field, Select, TextInput } from '../components/ui.jsx'
import StrengthMeter from '../components/StrengthMeter.jsx'
import { LockIcon, LogoMark, MailIcon, UserIcon } from '../components/icons.jsx'

const FALLBACK_TEAMS = ['Software Team', 'Hardware Team', 'Network Team', 'Security Team']

/**
 * Registration form.
 *
 * Two details worth noting:
 *
 *  1. The role list and the role-selection caveat come from
 *     `GET /api/auth/registration-policy`, not from a hardcoded array, so the
 *     form always matches what the server will accept.
 *  2. The backend returns 201 with no token, so `AuthContext.register()` signs
 *     in immediately afterwards and we can land the user on their portal.
 */
export default function Register() {
  const { register } = useAuth()
  const navigate = useNavigate()

  const [form, setForm] = useState({
    name: '',
    email: '',
    password: '',
    confirmPassword: '',
    role: 'employee',
    team: '',
  })
  const [policy, setPolicy] = useState(null)
  const [errors, setErrors] = useState({})
  const [formError, setFormError] = useState(null)
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    let cancelled = false
    authApi
      .registrationPolicy()
      .then((data) => {
        if (!cancelled) setPolicy(data)
      })
      .catch(() => {
        // Non-fatal: the form still works with the defaults above.
      })
    return () => {
      cancelled = true
    }
  }, [])

  const roles = policy?.valid_roles ?? ['admin', 'agent', 'employee']
  const teams = policy?.valid_teams?.length ? policy.valid_teams : FALLBACK_TEAMS

  function set(field, value) {
    setForm((current) => ({ ...current, [field]: value }))
  }

  async function onSubmit(event) {
    event.preventDefault()
    setErrors({})
    setFormError(null)

    if (form.password !== form.confirmPassword) {
      setErrors({ confirmPassword: 'Passwords do not match.' })
      return
    }

    setSubmitting(true)
    try {
      const profile = await register({
        name: form.name.trim(),
        email: form.email.trim(),
        password: form.password,
        role: form.role,
        // Only agents belong to a team; sending "" for other roles keeps the
        // payload honest instead of inventing a support team.
        team: form.role === 'agent' ? form.team : undefined,
      })
      navigate(HOME_FOR_ROLE[profile.role] ?? '/dashboard', { replace: true })
    } catch (error) {
      setFormError(error.message)
      setErrors(error.fields ?? {})
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="auth-canvas">
      <div className="relative z-10 w-full max-w-lg">
        <Link to="/login" className="mb-6 flex w-fit items-center gap-3">
          <LogoMark className="h-11 w-11" />
          <div>
            <h1 className="text-lg font-semibold tracking-tight text-ink">Create your account</h1>
            <p className="text-sm text-ink-muted">AutoDesk IT Support Portal</p>
          </div>
        </Link>

        <div className="card p-6 shadow-card-xl sm:p-8">
          {formError && (
            <div className="mb-5">
              <Alert tone="danger" title="Could not create the account">
                {formError}
              </Alert>
            </div>
          )}

          <form onSubmit={onSubmit} className="space-y-4" noValidate>
            <Field label="Full name" htmlFor="name" error={errors.name} required>
              <div className="relative">
                <UserIcon className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-faint" />
                <TextInput
                  id="name"
                  autoComplete="name"
                  autoFocus
                  placeholder="Priya Raman"
                  value={form.name}
                  onChange={(e) => set('name', e.target.value)}
                  error={errors.name}
                  className="pl-10"
                  required
                />
              </div>
            </Field>

            <Field label="Email address" htmlFor="email" error={errors.email} required>
              <div className="relative">
                <MailIcon className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-faint" />
                <TextInput
                  id="email"
                  type="email"
                  autoComplete="username"
                  placeholder="you@autodesk.local"
                  value={form.email}
                  onChange={(e) => set('email', e.target.value)}
                  error={errors.email}
                  className="pl-10"
                  required
                />
              </div>
            </Field>

            <Field
              label="Password"
              htmlFor="password"
              error={errors.password}
              hint="At least 8 characters, with upper and lower case letters and a digit."
              required
            >
              <div className="relative">
                <LockIcon className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-faint" />
                <TextInput
                  id="password"
                  type="password"
                  autoComplete="new-password"
                  value={form.password}
                  onChange={(e) => set('password', e.target.value)}
                  error={errors.password}
                  className="pl-10"
                  required
                />
              </div>
            </Field>

            <StrengthMeter password={form.password} />

            <Field
              label="Confirm password"
              htmlFor="confirmPassword"
              error={errors.confirmPassword}
              required
            >
              <div className="relative">
                <LockIcon className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-faint" />
                <TextInput
                  id="confirmPassword"
                  type="password"
                  autoComplete="new-password"
                  value={form.confirmPassword}
                  onChange={(e) => set('confirmPassword', e.target.value)}
                  error={errors.confirmPassword}
                  className="pl-10"
                  required
                />
              </div>
            </Field>

            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Role" htmlFor="role" error={errors.role}>
                <Select id="role" value={form.role} onChange={(e) => set('role', e.target.value)}>
                  {roles.map((role) => (
                    <option key={role} value={role}>
                      {role.charAt(0).toUpperCase() + role.slice(1)}
                    </option>
                  ))}
                </Select>
              </Field>

              <Field
                label="Support team"
                htmlFor="team"
                error={errors.team}
                hint={form.role === 'agent' ? 'Agents belong to a queue.' : 'Agents only.'}
              >
                <Select
                  id="team"
                  value={form.team}
                  disabled={form.role !== 'agent'}
                  onChange={(e) => set('team', e.target.value)}
                >
                  <option value="">
                    {form.role === 'agent' ? 'Select a team' : 'Not applicable'}
                  </option>
                  {teams.map((team) => (
                    <option key={team} value={team}>
                      {team}
                    </option>
                  ))}
                </Select>
              </Field>
            </div>

            <button type="submit" className="btn-primary mt-2 w-full py-2.5" disabled={submitting}>
              {submitting ? 'Creating account…' : 'Create account'}
            </button>
          </form>

          {policy?.production_note && (
            <div className="mt-5">
              <Alert tone="info" title="About role selection">
                {policy.production_note}
              </Alert>
            </div>
          )}

          <p className="mt-5 text-center text-sm text-ink-muted">
            Already registered?{' '}
            <Link to="/login" className="font-semibold text-brand-700 hover:underline">
              Sign in
            </Link>
          </p>
        </div>
      </div>
    </div>
  )
}
