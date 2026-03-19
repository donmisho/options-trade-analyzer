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

import { useState } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { MsalProvider } from '@azure/msal-react';
import { msalInstance } from './auth/msalConfig';
import { AppProvider } from './context/AppContext';
import { ToastProvider } from './components/Toast';
import Layout from './components/Layout';
import OptionsTerminal from './pages/OptionsTerminal';
// import VerticalsPage from './pages/VerticalsPage';      // DEPRECATED — retained for reference
// import NakedOptionsPage from './pages/NakedOptionsPage'; // DEPRECATED — retained for reference
// import FavoritesPage from './pages/FavoritesPage';  // DEPRECATED — /favorites redirects to /positions
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
  // activeStrategy drives OptionsTerminal — tabs in Header write to this state
  const [activeStrategy, setActiveStrategy] = useState('verticals');

  return (
    <MsalProvider instance={msalInstance}>
      <ToastProvider>
      <BrowserRouter>
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
                  <Layout setActiveStrategy={setActiveStrategy} />
                </AppProvider>
              </RequireAuth>
            }
          >
            {/* Dashboard — default home */}
            <Route path="/dashboard" element={<DashboardPage />} />

            {/* Strategy routes — all handled by OptionsTerminal */}
            <Route path="/verticals"     element={<OptionsTerminal activeStrategy={activeStrategy} />} />
            <Route path="/naked-options" element={<OptionsTerminal activeStrategy={activeStrategy} />} />

            {/* Security Dashboard — per-symbol strategy scorecard (legacy) */}
            <Route path="/security/:symbol" element={<Navigate to="/security-strategies" replace />} />

            {/* Security Strategies — primary landing page for a symbol */}
            <Route path="/security-strategies" element={<SecurityStrategiesPage />} />
            <Route path="/security-strategies/:symbol" element={<SecurityStrategiesPage />} />

            {/* Other pages */}
            <Route path="/directional" element={<Navigate to="/dashboard" replace />} />
            <Route path="/positions"   element={<PositionsPage />} />
            <Route path="/favorites"   element={<Navigate to="/positions" replace />} />

            {/* Default route → Dashboard */}
            <Route path="*" element={<Navigate to="/dashboard" replace />} />
          </Route>
        </Routes>
      </BrowserRouter>
      </ToastProvider>
    </MsalProvider>
  );
}
