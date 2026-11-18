import { Navigate, Route, Routes } from 'react-router-dom'
import { useAuth } from './context/AuthContext.jsx'
import AppShell from './components/AppShell.jsx'
import { ScreenLoader } from './components/ui.jsx'
import Login from './pages/Login.jsx'
import Register from './pages/Register.jsx'
import Notifications from './pages/Notifications.jsx'
import Forbidden from './pages/Forbidden.jsx'
import NotFound from './pages/NotFound.jsx'

import EmployeeDashboard from './pages/employee/Dashboard.jsx'
import EmployeeNewTicket from './pages/employee/NewTicket.jsx'
import EmployeeMyTickets from './pages/employee/MyTickets.jsx'
import EmployeeTicketDetail from './pages/employee/TicketDetail.jsx'

import AgentDashboard from './pages/agent/Dashboard.jsx'
import AgentQueue from './pages/agent/Queue.jsx'
import AgentMyTickets from './pages/agent/MyTickets.jsx'
import AgentTicketDetail from './pages/agent/TicketDetail.jsx'

import AdminDashboard from './pages/admin/Dashboard.jsx'
import AdminTickets from './pages/admin/Tickets.jsx'
import AdminTicketDetail from './pages/admin/TicketDetail.jsx'
import AdminAnalytics from './pages/admin/Analytics.jsx'
import AdminUsers from './pages/admin/Users.jsx'
import AdminMlStatus from './pages/admin/MlStatus.jsx'

/** Where each role lands after signing in. */
export const HOME_FOR_ROLE = {
  employee: '/dashboard',
  agent: '/agent',
  admin: '/admin',
}

/**
 * Route guard.
 *
 * This is a UX guard only. Every endpoint is independently protected by
 * `jwt_required()` and `role_required()` on the server, so tampering with this
 * check grants nothing.
 */
function RequireAuth({ roles, children }) {
  const { isAuthenticated, booting, role } = useAuth()

  if (booting) {
    return <ScreenLoader label="Checking your session" />
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />
  }

  if (roles && !roles.includes(role)) {
    return <Navigate to="/forbidden" replace />
  }

  return children
}

/** Signed-in users should not see the login or register screens. */
function PublicOnly({ children }) {
  const { isAuthenticated, booting, role } = useAuth()

  if (booting) return null
  if (isAuthenticated) return <Navigate to={HOME_FOR_ROLE[role] ?? '/dashboard'} replace />
  return children
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<PublicOnly><Login /></PublicOnly>} />
      <Route path="/register" element={<PublicOnly><Register /></PublicOnly>} />

      {/* ---- Employee portal ---- */}
      <Route
        element={
          <RequireAuth roles={['employee']}>
            <AppShell />
          </RequireAuth>
        }
      >
        <Route path="/dashboard" element={<EmployeeDashboard />} />
        <Route path="/tickets/new" element={<EmployeeNewTicket />} />
        <Route path="/tickets/my" element={<EmployeeMyTickets />} />
        <Route path="/tickets/:id" element={<EmployeeTicketDetail />} />
      </Route>

      {/* ---- Agent portal ---- */}
      <Route
        element={
          <RequireAuth roles={['agent', 'admin']}>
            <AppShell />
          </RequireAuth>
        }
      >
        <Route path="/agent" element={<AgentDashboard />} />
        <Route path="/agent/tickets" element={<AgentQueue />} />
        <Route path="/agent/my-tickets" element={<AgentMyTickets />} />
        <Route path="/agent/tickets/:id" element={<AgentTicketDetail />} />
      </Route>

      {/* ---- Admin portal ---- */}
      <Route
        element={
          <RequireAuth roles={['admin']}>
            <AppShell />
          </RequireAuth>
        }
      >
        <Route path="/admin" element={<AdminDashboard />} />
        <Route path="/admin/tickets" element={<AdminTickets />} />
        <Route path="/admin/tickets/:id" element={<AdminTicketDetail />} />
        <Route path="/admin/analytics" element={<AdminAnalytics />} />
        <Route path="/admin/users" element={<AdminUsers />} />
        <Route path="/admin/ml" element={<AdminMlStatus />} />
      </Route>

      {/* ---- Shared: every signed-in role ---- */}
      {/* Declared once, outside the role-guarded groups above. Repeating this
          path inside each group made the employee-scoped copy win for agents
          and admins, bouncing them to /forbidden. */}
      <Route
        element={
          <RequireAuth>
            <AppShell />
          </RequireAuth>
        }
      >
        <Route path="/notifications" element={<Notifications />} />
      </Route>

      <Route path="/forbidden" element={<Forbidden />} />
      <Route path="/" element={<Navigate to="/login" replace />} />
      <Route path="*" element={<NotFound />} />
    </Routes>
  )
}