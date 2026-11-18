import { useEffect, useState } from 'react'
import { authApi } from '../services/api'
import { CheckIcon } from './icons.jsx'

const CHECK_LABELS = {
  min_length: 'At least 8 characters',
  has_lower: 'A lowercase letter',
  has_upper: 'An uppercase letter',
  has_digit: 'A digit',
  has_symbol: 'A symbol',
  long_enough: '12 characters or more',
}

const BAR_TONES = [
  'bg-rose-500',
  'bg-rose-500',
  'bg-amber-500',
  'bg-emerald-500',
  'bg-emerald-500',
]

const TEXT_TONES = [
  'text-rose-600',
  'text-rose-600',
  'text-amber-600',
  'text-emerald-600',
  'text-emerald-600',
]

/**
 * Live password strength feedback.
 *
 * The score comes from the server (`POST /api/auth/password-strength`) rather
 * than being reimplemented here, so the bar always agrees with the validator
 * that will actually accept or reject the password. The request is debounced
 * and skipped entirely until the field is long enough to be worth scoring.
 */
export default function StrengthMeter({ password = '' }) {
  const [result, setResult] = useState(null)

  useEffect(() => {
    if (!password || password.length < 4) {
      setResult(null)
      return undefined
    }

    let cancelled = false
    const timer = setTimeout(() => {
      authApi
        .passwordStrength(password)
        .then((data) => {
          if (!cancelled) setResult(data)
        })
        .catch(() => {
          if (!cancelled) setResult(null)
        })
    }, 250)

    return () => {
      cancelled = true
      clearTimeout(timer)
    }
  }, [password])

  if (!password || !result) return null

  const score = result.score ?? 0

  return (
    <div className="rounded-xl border border-hairline bg-slate-50/80 p-3.5">
      <div className="flex items-center justify-between text-xs">
        <span className="font-medium text-ink-muted">Password strength</span>
        <span className={`font-semibold ${TEXT_TONES[score] ?? TEXT_TONES[0]}`}>{result.label}</span>
      </div>

      <div className="mt-2 flex gap-1.5" aria-hidden="true">
        {[0, 1, 2, 3].map((index) => (
          <span
            key={index}
            className={`h-1.5 flex-1 rounded-full transition-colors duration-300 ${
              index < score ? BAR_TONES[score] : 'bg-slate-300'
            }`}
          />
        ))}
      </div>

      <ul className="mt-3 grid gap-1.5 text-xs sm:grid-cols-2">
        {Object.entries(CHECK_LABELS).map(([key, label]) => {
          const met = result.checks?.[key]
          return (
            <li
              key={key}
              className={`flex items-center gap-1.5 ${met ? 'text-emerald-700' : 'text-ink-faint'}`}
            >
              <span
                aria-hidden="true"
                className={`flex h-3.5 w-3.5 shrink-0 items-center justify-center rounded-full ${
                  met ? 'bg-emerald-100 text-emerald-600' : 'bg-slate-200 text-slate-400'
                }`}
              >
                {met ? <CheckIcon className="h-2.5 w-2.5" /> : <span className="h-1 w-1 rounded-full bg-current" />}
              </span>
              {label}
            </li>
          )
        })}
      </ul>
    </div>
  )
}
