/**
 * Layout — The 2-column grid that wraps every page.
 *
 * WHY a Layout component?
 * Every screen in the app has the same structure: header across
 * the top, watchlist on the left, content on the right. Instead
 * of repeating this in every page, we define it once here.
 * React Router's <Outlet> renders whichever page matches the URL.
 *
 * Grid structure:
 *   ┌──────────────────────────────────────┐
 *   │              Header (nav tabs)       │
 *   ├──────────┬───────────────────────────┤
 *   │          │                           │
 *   │ Watchlist│   <Outlet> (page content) │
 *   │  160px   │                           │
 *   │          │                           │
 *   └──────────┴───────────────────────────┘
 */

import { Outlet } from 'react-router-dom';
import Header from './Header';
import Watchlist from './Watchlist';
import Toast from './Toast';
import TradeAgentPanel from './TradeAgentPanel';
import './Layout.css';

export default function Layout({ activeStrategy, setActiveStrategy }) {
  return (
    <div className="app-layout">
      <Header setActiveStrategy={setActiveStrategy} />
      <Watchlist />
      <main className="main-content">
        <Outlet />
      </main>
      <Toast />
      <TradeAgentPanel />
    </div>
  );
}
