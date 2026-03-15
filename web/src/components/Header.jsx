/**
 * Header — RETIRED (Phase 3.6 left-nav migration).
 *
 * All nav, Schwab status, settings, and sign-out now live in Layout.jsx's
 * left rail. This file is kept for reference but no longer imported.
 *
 * Original nav: Dashboard | Security Strategies | Verticals | Puts & Calls | Positions
 */
import { useState, useEffect, useCallback } from 'react';
import { NavLink, useNavigate } from 'react-router-dom';
import Logo from '../assets/Logo';
import { useApp } from '../context/AppContext';
import { getSchwabStatus, getSchwabAuthUrl } from '../api/client';
import './Header.css';

export default function Header({ setActiveStrategy }) {
  const { fetchPrices, setConfigOpen, activeSymbol } = useApp();
  const navigate = useNavigate();

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

  const handleSchwabClick = async () => {
    if (schwabConnected) return;
    const authUrl = await getSchwabAuthUrl();
    const popup = window.open(
      authUrl,
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

        <NavLink to="/dashboard" className={({ isActive }) => isActive ? 'nav-tab active' : 'nav-tab'}>
          Dashboard
        </NavLink>

        <button
          onClick={() => navigate(activeSymbol ? `/security-strategies/${activeSymbol}` : '/security-strategies')}
          className="nav-tab"
        >
          Security Strategies
        </button>

        <NavLink
          to="/verticals"
          className={({ isActive }) => isActive ? 'nav-tab active' : 'nav-tab'}
          onClick={() => setActiveStrategy?.('verticals')}
        >
          Verticals
        </NavLink>

        <NavLink
          to="/naked-options"
          className={({ isActive }) => isActive ? 'nav-tab active' : 'nav-tab'}
          onClick={() => setActiveStrategy?.('long-calls')}
        >
          Puts &amp; Calls
        </NavLink>

        <NavLink to="/positions" className={({ isActive }) => isActive ? 'nav-tab active' : 'nav-tab'}>
          Positions
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

        <button
          onClick={() => {
            localStorage.removeItem('ota_token');
            window.location.href = '/login';
          }}
          title="Log out"
          style={{
            background: 'none',
            border: '1px solid transparent',
            color: '#8b90a0',
            fontSize: 13,
            cursor: 'pointer',
            padding: '4px 8px',
            borderRadius: 6,
            transition: 'all 0.15s',
          }}
          onMouseEnter={(e) => { e.currentTarget.style.color = '#e4e7ef'; e.currentTarget.style.borderColor = '#252a3a'; }}
          onMouseLeave={(e) => { e.currentTarget.style.color = '#8b90a0'; e.currentTarget.style.borderColor = 'transparent'; }}
        >
          Sign out
        </button>
      </nav>
    </header>
  );
}
