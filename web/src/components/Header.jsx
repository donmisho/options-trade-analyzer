/**
 * Header — Top bar with logo, dynamic strategy tabs, favorites badge, Schwab status.
 *
 * Phase 2.7: Strategy tabs are now rendered dynamically from STRATEGY_CONFIGS.
 * Clicking a tab calls setActiveStrategy(cfg.key), which is passed down from App.jsx.
 * Favorites, Directional, and other routes remain as NavLinks.
 */
import { useState, useEffect, useCallback } from 'react';
import { NavLink, useNavigate } from 'react-router-dom';
import Logo from '../assets/Logo';
import { useApp } from '../context/AppContext';
import { getSchwabStatus, getSchwabAuthUrl } from '../api/client';
import { STRATEGY_CONFIGS } from '../strategy-configs/index';
import './Header.css';

export default function Header({ activeStrategy, setActiveStrategy }) {
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

  // Handle strategy tab click: update activeStrategy + navigate to the right URL
  const handleStrategyClick = (cfg) => {
    if (setActiveStrategy) setActiveStrategy(cfg.key);
    if (cfg.scorecardStrategy) {
      // Scorecard strategies route to SecurityDashboard for the current symbol
      navigate(activeSymbol ? `/security/${activeSymbol}` : '/dashboard');
    } else if (cfg.key === 'verticals') {
      navigate('/verticals');
    } else {
      navigate('/naked-options');
    }
  };

  return (
    <header className="header">
      <div className="logo">
        <Logo size={28} />
        <span>Options Analyzer</span>
      </div>
      <nav className="nav-tabs">

        {/* Dashboard */}
        <NavLink to="/dashboard" className="nav-tab">
          Dashboard
        </NavLink>

        {/* Dynamic strategy tabs from STRATEGY_CONFIGS */}
        {Object.values(STRATEGY_CONFIGS).map(cfg => (
          <button
            key={cfg.key}
            onClick={() => handleStrategyClick(cfg)}
            className={activeStrategy === cfg.key ? 'nav-tab active' : 'nav-tab'}
          >
            {cfg.tabLabel}
          </button>
        ))}

        {/* Non-strategy tabs remain as NavLinks */}
        <NavLink to="/directional" className="nav-tab">
          Directional Compare
        </NavLink>
        <NavLink to="/positions" className="nav-tab">
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
