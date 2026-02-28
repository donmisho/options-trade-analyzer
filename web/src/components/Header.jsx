/**
 * Header — Top bar with logo, nav tabs, favorites badge, and Schwab status.
 *
 * WHY NavLink instead of <a> tags?
 * React Router's NavLink automatically adds an "active" class
 * to the link that matches the current URL. This means the
 * blue underline on the active tab is handled by CSS alone —
 * no manual state tracking needed.
 *
 * SCHWAB STATUS INDICATOR:
 * Shows a small colored dot + label in the header that tells you
 * whether you're connected to Schwab. If disconnected, clicking
 * it takes you to the Schwab login flow. This saves you from
 * seeing "Network Error" and wondering why — the status is always
 * visible at a glance.
 */

import { useState, useEffect, useCallback } from 'react';
import { NavLink } from 'react-router-dom';
import Logo from '../assets/Logo';
import { useApp } from '../context/AppContext';
import { getSchwabStatus } from '../api/client';
import './Header.css';

export default function Header() {
  const { favorites } = useApp();
  const favCount = favorites.length;

  // Schwab connection state
  const [schwabConnected, setSchwabConnected] = useState(null); // null = checking

  const checkSchwabStatus = useCallback(async () => {
    try {
      const status = await getSchwabStatus();
      setSchwabConnected(status.connected === true);
    } catch {
      setSchwabConnected(false);
    }
  }, []);

  // Check on mount and every 5 minutes
  useEffect(() => {
    checkSchwabStatus();
    const interval = setInterval(checkSchwabStatus, 5 * 60 * 1000);
    return () => clearInterval(interval);
  }, [checkSchwabStatus]);

  const handleSchwabClick = () => {
    if (!schwabConnected) {
      // Open the Schwab OAuth login flow
      // WHY window.open? The OAuth flow redirects through Schwab's site
      // and back to our callback URL. Opening in the same tab would
      // lose the user's current analysis state.
      window.location.href = '/api/v1/auth/schwab/login';
    }
  };

  return (
    <header className="header">
      <div className="logo">
        <Logo size={28} />
        <span>Options Analyzer</span>
      </div>
      <nav className="nav-tabs">
        <NavLink to="/verticals" className="nav-tab">
          Vertical Spreads
        </NavLink>
        <NavLink to="/long-calls" className="nav-tab">
          Long Calls
        </NavLink>
        <NavLink to="/directional" className="nav-tab">
          Directional Compare
        </NavLink>
        <NavLink to="/favorites" className="nav-tab">
          ★ Favorites
          {favCount > 0 && <span className="fav-count">{favCount}</span>}
        </NavLink>
        <div
          className={`schwab-status ${
            schwabConnected === null ? 'checking' :
            schwabConnected ? 'connected' : 'disconnected'
          }`}
          onClick={handleSchwabClick}
          title={
            schwabConnected === null ? 'Checking Schwab connection...' :
            schwabConnected ? 'Connected to Schwab' :
            'Click to connect to Schwab'
          }
        >
          <span className="schwab-dot" />
          <span className="schwab-label">
            {schwabConnected === null ? '...' :
             schwabConnected ? 'Schwab' : 'Disconnected'}
          </span>
        </div>
      </nav>
    </header>
  );
}
