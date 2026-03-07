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
 * React Router v6 nested layout: <Layout> renders header + watchlist + <Outlet>.
 * /login and /connect render outside Layout (no header/watchlist).
 */

import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { MsalProvider } from '@azure/msal-react';
import { msalInstance } from './auth/msalConfig';
import { AppProvider } from './context/AppContext';
import Layout from './components/Layout';
import VerticalsPage from './pages/VerticalsPage';
import NakedOptionsPage from './pages/NakedOptionsPage';
import DirectionalPage from './pages/DirectionalPage';
import FavoritesPage from './pages/FavoritesPage';
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
            <Route path="/verticals" element={<VerticalsPage />} />
            <Route path="/naked-options" element={<NakedOptionsPage />} />
            <Route path="/directional" element={<DirectionalPage />} />
            <Route path="/favorites" element={<FavoritesPage />} />
            {/* Default route → Vertical Spreads */}
            <Route path="*" element={<Navigate to="/verticals" replace />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </MsalProvider>
  );
}
