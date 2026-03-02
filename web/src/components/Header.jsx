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
 * whether you're connected to Schwab's market data API.
 *
 * - "Connected" (green) = Schwab OAuth tokens are valid, live data flows
 * - "Disconnected" (red) = tokens expired or missing — click to log in
 * - "..." (gray) = checking status on first load
 *
 * WHY open in a popup instead of navigating away?
 * The Schwab OAuth flow redirects through Schwab's login page and back
 * to our callback URL. If we navigated in the same tab, the user would
 * lose whatever analysis they had open. A popup keeps their work intact
 * and auto-detects when login completes by polling the status endpoint.
 */
import { useState, useEffect, useCallback } from 'react';
import { NavLink } from 'react-router-dom';
import Logo from '../assets/Logo';
import { useApp } from '../context/AppContext';
import { getSchwabStatus } from '../api/client';
import './Header.css';

export default function Header() {
  const { favorites, fetchPrices } = useApp();
  const favCount = favorites.length;

  // Schwab connection state: null = checking, true = connected, false = disconnected
  const [schwabConnected, setSchwabConnected] = useState(null);

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

  /**
   * WHY a popup + polling pattern?
   *
   * 1. We open Schwab's OAuth login in a small popup window
   * 2. The user logs in on Schwab's site
   * 3. Schwab redirects back to our backend callback URL, which stores tokens
   * 4. Meanwhile, we poll /auth/schwab/status every 2 seconds
   * 5. Once it returns connected=true, we update the indicator and close the popup
   *
   * This avoids navigating away from the app and losing the user's current work.
   */
  const handleSchwabClick = () => {
    if (schwabConnected) return; // Already connected, nothing to do

    // Open the Schwab login in a popup window.
    // WHY https://127.0.0.1:8000 (backend) instead of relative URL?
    // The OAuth callback URL registered with Schwab points to the backend directly.
    // The Vite dev server (port 5173) can't handle the OAuth redirect.
    const popup = window.open(
      'https://127.0.0.1:8000/api/v1/auth/schwab/login',
      'schwab-login',
      'width=600,height=700,menubar=no,toolbar=no'
    );

    // Poll for connection status every 2 seconds while popup is open
    const pollInterval = setInterval(async () => {
      try {
        // Check if user closed the popup manually
        if (popup && popup.closed) {
          clearInterval(pollInterval);
          // Do one final check — they might have completed login before closing
          await checkSchwabStatus();
          return;
        }
        const status = await getSchwabStatus();
        if (status.connected) {
          setSchwabConnected(true);
          clearInterval(pollInterval);
          // Auto-close the popup since login succeeded
          if (popup && !popup.closed) popup.close();
          // Refresh watchlist prices now that we have a valid token
          fetchPrices();
        }
      } catch {
        // Keep polling — network hiccups during OAuth are normal
      }
    }, 2000);

    // Safety net: stop polling after 5 minutes no matter what
    // (prevents runaway intervals if something goes wrong)
    setTimeout(() => clearInterval(pollInterval), 5 * 60 * 1000);
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
          style={{ cursor: schwabConnected ? 'default' : 'pointer' }}
          title={
            schwabConnected === null ? 'Checking Schwab connection...' :
            schwabConnected ? 'Connected to Schwab — live market data active' :
            'Click to connect to Schwab'
          }
        >
          <span className="schwab-dot" />
          <span className="schwab-label">
            {schwabConnected === null ? '...' :
             schwabConnected ? 'Connected' : 'Disconnected'}
          </span>
        </div>
      </nav>
    </header>
  );
}
