/**
 * App — Root component that wires together routing and shared state.
 *
 * Auth flow:
 *  - AuthContext checks /auth/me on mount — shows login page if not authenticated
 *  - /login → redirect to backend /api/v1/auth/login → Entra → callback → cookie set
 *  - Cookie is sent automatically via credentials: 'include' on all API calls
 *  - 401 from any API call → apiFetch auto-redirects to root (shows login page)
 *
 * HOW ROUTING WORKS:
 * React Router v6 nested layout: <Layout> renders the left nav rail + <Outlet>.
 */

import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AppProvider } from './context/AppContext';
import { ToastProvider } from './components/Toast';
import Layout from './components/Layout';
import TradesPage from './pages/TradesPage';
import StrategyPage from './pages/StrategyPage';
import PositionsPage from './pages/PositionsPage';
import DashboardPage from './pages/DashboardPage';
import SecurityStrategiesPage from './pages/SecurityStrategiesPage';
import BrokerConnectPage from './pages/BrokerConnectPage';
import ChangeLogPage from './pages/ChangeLogPage';

export default function App() {
  return (
    <BrowserRouter>
      <ToastProvider>
        <Routes>
          {/* /connect renders outside Layout (no nav chrome) */}
          <Route path="/connect" element={<BrokerConnectPage />} />

          {/* All protected routes — AppProvider wraps the layout */}
          <Route
            element={
              <AppProvider>
                <Layout />
              </AppProvider>
            }
          >
            {/* Dashboard — default home */}
            <Route path="/dashboard" element={<DashboardPage />} />

            {/* Trades — primary trade-finding screen */}
            <Route path="/trades" element={<TradesPage />} />

            {/* Redirects from retired routes */}
            <Route path="/verticals"     element={<Navigate to="/trades" replace />} />
            <Route path="/naked-options" element={<Navigate to="/trades" replace />} />
            <Route path="/puts-calls"    element={<Navigate to="/trades" replace />} />
            <Route path="/long-calls"    element={<Navigate to="/trades" replace />} />

            {/* Security Dashboard — legacy redirect */}
            <Route path="/security/:symbol" element={<Navigate to="/security-strategies" replace />} />

            {/* Security Strategies — primary landing page for a symbol */}
            <Route path="/security-strategies" element={<SecurityStrategiesPage />} />
            <Route path="/security-strategies/:symbol" element={<SecurityStrategiesPage />} />

            {/* Strategy pages */}
            <Route path="/strategies/:key" element={<StrategyPage />} />

            {/* Other pages */}
            <Route path="/directional" element={<Navigate to="/dashboard" replace />} />
            <Route path="/positions"   element={<PositionsPage />} />
            <Route path="/favorites"   element={<Navigate to="/positions" replace />} />
            <Route path="/changelog"   element={<ChangeLogPage />} />

            {/* Default route → Dashboard */}
            <Route path="*" element={<Navigate to="/dashboard" replace />} />
          </Route>
        </Routes>
      </ToastProvider>
    </BrowserRouter>
  );
}
