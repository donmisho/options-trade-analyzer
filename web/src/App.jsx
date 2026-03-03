/**
 * App — Root component that wires together routing and shared state.
 *
 * HOW ROUTING WORKS:
 * React Router v6 uses a nested layout pattern. The <Layout> component
 * renders the header + watchlist + an <Outlet> placeholder. The child
 * routes (VerticalsPage, LongCallsPage, etc.) render inside that Outlet.
 * This means the header and watchlist are always visible, and only the
 * main content area changes when you click a tab.
 *
 * The "/" redirect sends you to /verticals by default — this is the
 * first screen you see when you open the app.
 */

import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AppProvider } from './context/AppContext';
import Layout from './components/Layout';
import VerticalsPage from './pages/VerticalsPage';
import NakedOptionsPage from './pages/NakedOptionsPage';
import DirectionalPage from './pages/DirectionalPage';
import FavoritesPage from './pages/FavoritesPage';

export default function App() {
  return (
    <BrowserRouter>
      <AppProvider>
        <Routes>
          <Route element={<Layout />}>
            <Route path="/verticals" element={<VerticalsPage />} />
            <Route path="/naked-options" element={<NakedOptionsPage />} />
            <Route path="/directional" element={<DirectionalPage />} />
            <Route path="/favorites" element={<FavoritesPage />} />
            {/* Default route → Vertical Spreads */}
            <Route path="*" element={<Navigate to="/verticals" replace />} />
          </Route>
        </Routes>
      </AppProvider>
    </BrowserRouter>
  );
}
