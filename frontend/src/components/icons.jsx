/**
 * Icon set.
 *
 * The project has no icon dependency, so the icons the UI needs live here as
 * inline SVG paths. They are all drawn on a 24x24 grid with a 1.75 stroke so
 * they sit optically consistent next to 13–14px text.
 *
 * Every icon is decorative: callers supply the meaning as text (or an
 * `aria-label` on a button), so each one renders `aria-hidden`.
 */
import { useId } from 'react'

function Svg({ className = 'h-5 w-5', children, ...rest }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.75}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
      className={className}
      {...rest}
    >
      {children}
    </svg>
  )
}

// ---------------------------------------------------------------------------
// Navigation & structure
// ---------------------------------------------------------------------------
export const HomeIcon = (p) => (
  <Svg {...p}>
    <path d="M3 10.5 12 3l9 7.5" />
    <path d="M5 9.6V20a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1V9.6" />
    <path d="M9.5 21v-5.5h5V21" />
  </Svg>
)

export const GaugeIcon = (p) => (
  <Svg {...p}>
    <path d="M12 14.5 15.5 10" />
    <path d="M3.6 17a9 9 0 1 1 16.8 0" />
    <circle cx="12" cy="17" r="1.4" />
  </Svg>
)

export const TicketIcon = (p) => (
  <Svg {...p}>
    <path d="M3 9.2V7a1 1 0 0 1 1-1h16a1 1 0 0 1 1 1v2.2a2.3 2.3 0 0 0 0 4.6V16a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1v-2.2a2.3 2.3 0 0 0 0-4.6Z" />
    <path d="M13 6v2M13 11v2M13 16v2" />
  </Svg>
)

export const InboxIcon = (p) => (
  <Svg {...p}>
    <path d="M4 13h4l1.4 2.4h5.2L16 13h4" />
    <path d="M4 13 6.3 5.4A1.5 1.5 0 0 1 7.7 4.5h8.6a1.5 1.5 0 0 1 1.4.9L20 13v4.6a1.5 1.5 0 0 1-1.5 1.4h-13A1.5 1.5 0 0 1 4 17.6Z" />
  </Svg>
)

export const BellIcon = (p) => (
  <Svg {...p}>
    <path d="M18 9a6 6 0 1 0-12 0c0 4-1.6 5.2-2 5.7h16C19.6 14.2 18 13 18 9Z" />
    <path d="M13.7 18.5a2 2 0 0 1-3.4 0" />
  </Svg>
)

export const UsersIcon = (p) => (
  <Svg {...p}>
    <circle cx="9" cy="8" r="3.2" />
    <path d="M3.5 19.2a5.5 5.5 0 0 1 11 0" />
    <path d="M16 5.2a3.2 3.2 0 0 1 0 5.9" />
    <path d="M17.2 14.4a5.5 5.5 0 0 1 3.3 4.8" />
  </Svg>
)

export const ChartIcon = (p) => (
  <Svg {...p}>
    <path d="M4 20V4" />
    <path d="M4 20h16" />
    <rect x="7" y="12" width="3" height="5" rx="0.8" />
    <rect x="12.5" y="8" width="3" height="9" rx="0.8" />
    <rect x="18" y="5" width="3" height="12" rx="0.8" />
  </Svg>
)

export const CpuIcon = (p) => (
  <Svg {...p}>
    <rect x="6.5" y="6.5" width="11" height="11" rx="2" />
    <rect x="9.75" y="9.75" width="4.5" height="4.5" rx="1" />
    <path d="M10 3v3.5M14 3v3.5M10 17.5V21M14 17.5V21M3 10h3.5M3 14h3.5M17.5 10H21M17.5 14H21" />
  </Svg>
)

export const LayersIcon = (p) => (
  <Svg {...p}>
    <path d="m12 3.5 8.5 4.3-8.5 4.4-8.5-4.4Z" />
    <path d="m4 12 8 4.1 8-4.1" />
    <path d="m4 16.4 8 4.1 8-4.1" />
  </Svg>
)

export const ShieldIcon = (p) => (
  <Svg {...p}>
    <path d="M12 3 5 5.8v5.4c0 4.3 2.9 8 7 9.3 4.1-1.3 7-5 7-9.3V5.8Z" />
    <path d="m9 12 2 2 4-4" />
  </Svg>
)

// ---------------------------------------------------------------------------
// Actions
// ---------------------------------------------------------------------------
export const PlusIcon = (p) => (
  <Svg {...p}>
    <path d="M12 5.5v13M5.5 12h13" />
  </Svg>
)

export const SearchIcon = (p) => (
  <Svg {...p}>
    <circle cx="11" cy="11" r="6.5" />
    <path d="m16 16 4 4" />
  </Svg>
)

export const FilterIcon = (p) => (
  <Svg {...p}>
    <path d="M4 6h16l-6.2 7.2V19l-3.6-2v-3.8Z" />
  </Svg>
)

export const RefreshIcon = (p) => (
  <Svg {...p}>
    <path d="M20 11a8 8 0 1 0-.9 4.6" />
    <path d="M20 5.5V11h-5.5" />
  </Svg>
)

export const PrintIcon = (p) => (
  <Svg {...p}>
    <path d="M7 9V4h10v5" />
    <path d="M7 18H5.5A1.5 1.5 0 0 1 4 16.5v-4A1.5 1.5 0 0 1 5.5 11h13a1.5 1.5 0 0 1 1.5 1.5v4a1.5 1.5 0 0 1-1.5 1.5H17" />
    <rect x="7" y="14.5" width="10" height="6" rx="1" />
  </Svg>
)

export const MenuIcon = (p) => (
  <Svg {...p}>
    <path d="M4 7h16M4 12h16M4 17h16" />
  </Svg>
)

export const CloseIcon = (p) => (
  <Svg {...p}>
    <path d="m6.5 6.5 11 11M17.5 6.5l-11 11" />
  </Svg>
)

export const ChevronRightIcon = (p) => (
  <Svg {...p}>
    <path d="m9.5 5.5 6.5 6.5-6.5 6.5" />
  </Svg>
)

export const ChevronLeftIcon = (p) => (
  <Svg {...p}>
    <path d="M14.5 5.5 8 12l6.5 6.5" />
  </Svg>
)

export const ChevronDownIcon = (p) => (
  <Svg {...p}>
    <path d="m5.5 9 6.5 6.5L18.5 9" />
  </Svg>
)

export const ArrowRightIcon = (p) => (
  <Svg {...p}>
    <path d="M4.5 12h15" />
    <path d="m13.5 6 6 6-6 6" />
  </Svg>
)

export const ArrowLeftIcon = (p) => (
  <Svg {...p}>
    <path d="M19.5 12h-15" />
    <path d="m10.5 6-6 6 6 6" />
  </Svg>
)

export const LogOutIcon = (p) => (
  <Svg {...p}>
    <path d="M14.5 16.5v2A1.5 1.5 0 0 1 13 20H6.5A1.5 1.5 0 0 1 5 18.5v-13A1.5 1.5 0 0 1 6.5 4H13a1.5 1.5 0 0 1 1.5 1.5v2" />
    <path d="M10 12h10" />
    <path d="m17 8.5 3.5 3.5L17 15.5" />
  </Svg>
)

export const EditIcon = (p) => (
  <Svg {...p}>
    <path d="M4 20h4l10-10-4-4L4 16Z" />
    <path d="m14.5 5.5 4 4" />
  </Svg>
)

export const DownloadIcon = (p) => (
  <Svg {...p}>
    <path d="M12 4v11" />
    <path d="m7.5 10.5 4.5 4.5 4.5-4.5" />
    <path d="M4.5 19.5h15" />
  </Svg>
)

export const ExternalLinkIcon = (p) => (
  <Svg {...p}>
    <path d="M14 4h6v6" />
    <path d="m20 4-8.5 8.5" />
    <path d="M18 14.5V19a1.5 1.5 0 0 1-1.5 1.5H5A1.5 1.5 0 0 1 3.5 19V7.5A1.5 1.5 0 0 1 5 6h4.5" />
  </Svg>
)

export const SendIcon = (p) => (
  <Svg {...p}>
    <path d="M20 4 3.8 10.4a.6.6 0 0 0 0 1.1l6.6 2.5 2.5 6.6a.6.6 0 0 0 1.1 0Z" />
    <path d="M20 4 10.4 14" />
  </Svg>
)

export const SparklesIcon = (p) => (
  <Svg {...p}>
    <path d="M12 4.5 13.6 9 18 10.5 13.6 12 12 16.5 10.4 12 6 10.5 10.4 9Z" />
    <path d="M18.5 16.5 19.2 18.6 21.3 19.3 19.2 20 18.5 22.1 17.8 20 15.7 19.3 17.8 18.6Z" />
  </Svg>
)

export const WandIcon = (p) => (
  <Svg {...p}>
    <path d="m5 19 9-9" />
    <path d="m14.5 5.5 4 4" />
    <path d="M17 3v2.5M17 8.5V11M20.5 5.5H23M20 5.5H17" />
  </Svg>
)

// ---------------------------------------------------------------------------
// Status & feedback
// ---------------------------------------------------------------------------
export const CheckIcon = (p) => (
  <Svg {...p}>
    <path d="m5 12.5 4.5 4.5L19 7" />
  </Svg>
)

export const CheckCircleIcon = (p) => (
  <Svg {...p}>
    <circle cx="12" cy="12" r="8.5" />
    <path d="m8.5 12.2 2.4 2.4 4.6-5" />
  </Svg>
)

export const AlertTriangleIcon = (p) => (
  <Svg {...p}>
    <path d="M12 4.5 21 19H3Z" />
    <path d="M12 10v4" />
    <path d="M12 16.8h.01" />
  </Svg>
)

export const AlertCircleIcon = (p) => (
  <Svg {...p}>
    <circle cx="12" cy="12" r="8.5" />
    <path d="M12 8v5" />
    <path d="M12 15.8h.01" />
  </Svg>
)

export const InfoIcon = (p) => (
  <Svg {...p}>
    <circle cx="12" cy="12" r="8.5" />
    <path d="M12 11v5" />
    <path d="M12 8.2h.01" />
  </Svg>
)

export const HelpCircleIcon = (p) => (
  <Svg {...p}>
    <circle cx="12" cy="12" r="8.5" />
    <path d="M9.6 9.6a2.4 2.4 0 1 1 3.2 2.3c-.6.3-.8.7-.8 1.4" />
    <path d="M12 16.6h.01" />
  </Svg>
)

export const ClockIcon = (p) => (
  <Svg {...p}>
    <circle cx="12" cy="12" r="8.5" />
    <path d="M12 7.5V12l3 1.8" />
  </Svg>
)

export const TrendUpIcon = (p) => (
  <Svg {...p}>
    <path d="m4 16.5 5.5-5.5 3.5 3.5L20 7.5" />
    <path d="M15.5 7.5H20V12" />
  </Svg>
)

export const ActivityIcon = (p) => (
  <Svg {...p}>
    <path d="M3.5 12.5h3l2.5-6 4 12 2.5-6h5" />
  </Svg>
)

export const TargetIcon = (p) => (
  <Svg {...p}>
    <circle cx="12" cy="12" r="8.5" />
    <circle cx="12" cy="12" r="4.5" />
    <circle cx="12" cy="12" r="1" />
  </Svg>
)

export const AwardIcon = (p) => (
  <Svg {...p}>
    <circle cx="12" cy="9" r="5.5" />
    <path d="m8.5 13.5-1 7 4.5-2.5 4.5 2.5-1-7" />
  </Svg>
)

export const LockIcon = (p) => (
  <Svg {...p}>
    <rect x="4.5" y="10" width="15" height="10" rx="2" />
    <path d="M8 10V7.5a4 4 0 0 1 8 0V10" />
  </Svg>
)

export const MailIcon = (p) => (
  <Svg {...p}>
    <rect x="3.5" y="5.5" width="17" height="13" rx="2" />
    <path d="m4 7 8 5.5L20 7" />
  </Svg>
)

export const UserIcon = (p) => (
  <Svg {...p}>
    <circle cx="12" cy="8.5" r="3.5" />
    <path d="M5 19.5a7 7 0 0 1 14 0" />
  </Svg>
)

export const FileTextIcon = (p) => (
  <Svg {...p}>
    <path d="M13.5 3.5H7A1.5 1.5 0 0 0 5.5 5v14A1.5 1.5 0 0 0 7 20.5h10a1.5 1.5 0 0 0 1.5-1.5V8.5Z" />
    <path d="M13.5 3.5V9h5" />
    <path d="M9 13h6M9 16.5h4" />
  </Svg>
)

export const DatabaseIcon = (p) => (
  <Svg {...p}>
    <ellipse cx="12" cy="6.5" rx="7" ry="2.8" />
    <path d="M5 6.5v11c0 1.5 3.1 2.8 7 2.8s7-1.3 7-2.8v-11" />
    <path d="M5 12c0 1.5 3.1 2.8 7 2.8s7-1.3 7-2.8" />
  </Svg>
)

export const ListChecksIcon = (p) => (
  <Svg {...p}>
    <path d="m3.5 6.5 1.8 1.8L8.5 5" />
    <path d="m3.5 13 1.8 1.8L8.5 11.5" />
    <path d="M12 6.5h8.5M12 13h8.5M12 19h8.5" />
    <path d="m3.5 19.5 1.8 1.8 3.2-3.3" />
  </Svg>
)

export const EyeIcon = (p) => (
  <Svg {...p}>
    <path d="M2.5 12S6 6.5 12 6.5 21.5 12 21.5 12 18 17.5 12 17.5 2.5 12 2.5 12Z" />
    <circle cx="12" cy="12" r="2.8" />
  </Svg>
)

export const HandIcon = (p) => (
  <Svg {...p}>
    <path d="M9 11V5.5a1.5 1.5 0 0 1 3 0V11" />
    <path d="M12 10.5V4.8a1.5 1.5 0 0 1 3 0V11" />
    <path d="M15 11V7.3a1.5 1.5 0 0 1 3 0V14a6 6 0 0 1-6 6h-.8a5 5 0 0 1-3.8-1.8L4.6 14a1.6 1.6 0 0 1 2.4-2L9 14.2V8.5a1.5 1.5 0 0 1 0-3" />
  </Svg>
)

/** Diagonal "up-right" arrow, used as a row affordance. */
export const ArrowUpRightIcon = (p) => (
  <Svg {...p}>
    <path d="M7.5 16.5 16.5 7.5" />
    <path d="M9 7.5h7.5V15" />
  </Svg>
)

/**
 * The product mark: a ticket shape with a neural-node dot pattern.
 * Used in the sidebar, the auth screens and as the favicon.
 */
export function LogoMark({ className = 'h-9 w-9' }) {
  const gradientId = useId()
  return (
    <svg viewBox="0 0 40 40" className={className} role="img" aria-label="AutoDesk">
      <defs>
        <linearGradient id={gradientId} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor="#4a68f5" />
          <stop offset="100%" stopColor="#7c2ce0" />
        </linearGradient>
      </defs>
      <rect width="40" height="40" rx="11" fill={`url(#${gradientId})`} />
      <path
        d="M12 13.5h16a1 1 0 0 1 1 1v3.2a2.2 2.2 0 0 0 0 4.6v3.2a1 1 0 0 1-1 1H12a1 1 0 0 1-1-1v-3.2a2.2 2.2 0 0 0 0-4.6v-3.2a1 1 0 0 1 1-1Z"
        fill="none"
        stroke="white"
        strokeWidth="1.8"
        strokeLinejoin="round"
        opacity="0.95"
      />
      <circle cx="16" cy="20" r="2.1" fill="white" />
      <circle cx="24.5" cy="16.4" r="1.4" fill="white" opacity="0.85" />
      <circle cx="24.5" cy="23.6" r="1.4" fill="white" opacity="0.85" />
    </svg>
  )
}
