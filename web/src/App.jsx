/**
 * App — Root component that wires together routing and shared state.
 *
 * Auth flow:
 *  - No JWT in localStorage → redirect to /login (RequireAuth guard)
 *  - /login → Entra popup → our JWT stored → redirect to /connect or /verticals
 *  - /connect → Schwab OAuth popup → on success → /verticals
 *  - JWT 401 from any API call → apiFetch auto-redirects to /login
 *
 * HOW ROUTING WORKS:
 * React Router v6 nested layout: <Layout> renders the left nav rail + <Outlet>.
 * /login and /connect render outside Layout (no nav chrome).
 *
 * activeStrategy (lives here) controls which config OptionsTerminal uses.
 * Layout's nav items call setActiveStrategy on click.
 */

import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { MsalProvider } from '@azure/msal-react';
import { msalInstance } from './auth/msalConfig';
import { AppProvider } from './context/AppContext';
import { ToastProvider } from './components/Toast';
import Layout from './components/Layout';
import TradesPage from './pages/TradesPage';
import StrategyPage from './pages/StrategyPage';
import PositionsPage from './pages/PositionsPage';
import DashboardPage from './pages/DashboardPage';
import SecurityStrategiesPage from './pages/SecurityStrategiesPage';
import LoginPage from './pages/LoginPage';
import BrokerConnectPage from './pages/BrokerConnectPage';

/** Decode the exp claim from a JWT without a library. Returns 0 if unreadable. */
function getTokenExpiry(token) {
  try {
    const payload = JSON.parse(atob(token.split('.')[1]));
    return payload.exp || 0;
  } catch {
    return 0;
  }
}

/** Redirect unauthenticated or expired sessions to /login. */
function RequireAuth({ children }) {
  const token = localStorage.getItem('ota_token');
  if (!token) return <Navigate to="/login" replace />;

  const exp = getTokenExpiry(token);
  if (exp && Date.now() / 1000 > exp) {
    localStorage.removeItem('ota_token');
    return <Navigate to="/login" replace />;
  }

  return children;
}

export default function App() {
  return (
    <MsalProvider instance={msalInstance}>
      <BrowserRouter>
      <ToastProvider>
        <Routes>
          {/* Public routes — no auth, no AppContext, no Layout chrome */}
          <Route path="/login" element={<LoginPage />} />
          <Route
            path="/connect"
            element={
              <RequireAuth>
                <BrokerConnectPage />
              </RequireAuth>
            }
          />

          {/* Protected routes — AppProvider only mounts when authenticated */}
          <Route
            element={
              <RequireAuth>
                <AppProvider>
                  <Layout />
                </AppProvider>
              </RequireAuth>
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

            {/* Security Dashboard — per-symbol strategy scorecard (legacy) */}
            <Route path="/security/:symbol" element={<Navigate to="/security-strategies" replace />} />

            {/* Security Strategies — primary landing page for a symbol */}
            <Route path="/security-strategies" element={<SecurityStrategiesPage />} />
            <Route path="/security-strategies/:symbol" element={<SecurityStrategiesPage />} />

            {/* Strategy pages — per-strategy detail (placeholder, wired in later session) */}
            <Route path="/strategies/:key" element={<StrategyPage />} />

            {/* Other pages */}
            <Route path="/directional" element={<Navigate to="/dashboard" replace />} />
            <Route path="/positions"   element={<PositionsPage />} />
            <Route path="/favorites"   element={<Navigate to="/positions" replace />} />

            {/* Default route → Dashboard */}
            <Route path="*" element={<Navigate to="/dashboard" replace />} />
          </Route>
        </Routes>
      </ToastProvider>
      </BrowserRouter>
    </MsalProvider>
  );
}
