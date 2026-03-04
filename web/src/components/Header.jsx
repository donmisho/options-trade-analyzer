/**
 * Header — Top bar with logo, nav tabs, favorites badge, and Schwab status.
 *
 * ROUND 4 CHANGE: "Long Calls" tab renamed to "Puts & Calls" with
 * route path changed from /long-calls to /naked-options.
 */
import { useState, useEffect, useCallback } from 'react';
import { NavLink } from 'react-router-dom';
import Logo from '../assets/Logo';
import { useApp } from '../context/AppContext';
import { getSchwabStatus } from '../api/client';
import './Header.css';

export default function Header() {
  const { favorites, fetchPrices, setConfigOpen } = useApp();
  const favCount = favorites.length;

  const [schwabConnected, setSchwabConnected] = useState(null);

  const checkSchwabStatus = useCallback(async () => {
    try {
      const status = await getSchwabStatus();
      setSchwabConnected(status.connected === true);
    } catch {
      setSchwabConnected(false);
    }
  }, []);

  useEffect(() => {
    checkSchwabStatus();
    const interval = setInterval(checkSchwabStatus, 5 * 60 * 1000);
    return () => clearInterval(interval);
  }, [checkSchwabStatus]);

  const handleSchwabClick = () => {
    if (schwabConnected) return;
    const popup = window.open(
      `${import.meta.env.VITE_API_BASE_URL || 'https://127.0.0.1:8000'}/api/v1/auth/schwab/login`,
      'schwab-login',
      'width=600,height=700,menubar=no,toolbar=no'
    );
    const pollInterval = setInterval(async () => {
      try {
        if (popup && popup.closed) {
          clearInterval(pollInterval);
          await checkSchwabStatus();
          return;
        }
        const status = await getSchwabStatus();
        if (status.connected) {
          setSchwabConnected(true);
          clearInterval(pollInterval);
          if (popup && !popup.closed) popup.close();
          fetchPrices();
        }
      } catch { /* Keep polling */ }
    }, 2000);
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
        {/* CHANGED: was /long-calls "Long Calls" — now covers both puts and calls */}
        <NavLink to="/naked-options" className="nav-tab">
          Puts & Calls
        </NavLink>
        <NavLink to="/directional" className="nav-tab">
          Directional Compare
        </NavLink>
        <NavLink to="/favorites" className="nav-tab">
          ★ Favorites
          {favCount > 0 && <span className="fav-count">{favCount}</span>}
        </NavLink>
         <button
          onClick={() => setConfigOpen(true)}
          title="Analysis configuration"
          style={{
            background: 'none',
            border: '1px solid transparent',
            color: '#8b90a0',
            fontSize: 18,
            cursor: 'pointer',
            padding: '4px 8px',
            borderRadius: 6,
            transition: 'all 0.15s',
            display: 'flex',
            alignItems: 'center',
          }}
          onMouseEnter={(e) => { e.currentTarget.style.color = '#e4e7ef'; e.currentTarget.style.borderColor = '#252a3a'; }}
          onMouseLeave={(e) => { e.currentTarget.style.color = '#8b90a0'; e.currentTarget.style.borderColor = 'transparent'; }}
        >
          ⚙
        </button>       
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
