/**
 * Layout — Fixed left rail (220px) + main content area.
 *
 * Replaces the old header-top / watchlist-left grid.
 * All nav, Schwab status, settings, and sign-out live in the rail.
 * The Watchlist is a collapsible panel toggled from the top-right of the content zone.
 *
 * Rail sections (top → bottom):
 *   1. Logo — links to /dashboard
 *   2. Nav items — Dashboard · Security Strategies · Verticals · Puts & Calls · Positions
 *   3. Bottom — Schwab indicator · Settings gear · Sign out
 *
 * Strategy note: clicking Verticals or Puts & Calls also calls setActiveStrategy()
 * so OptionsTerminal receives the correct config.
 */

import { useState, useEffect, useCallback } from 'react';
import { Outlet, useLocation, useNavigate } from 'react-router-dom';
import Logo from '../assets/Logo';
import Watchlist from './Watchlist';
import Toast from './Toast';
import TradeAgentPanel from './TradeAgentPanel';
import { useApp } from '../context/AppContext';
import { getSchwabStatus, getSchwabAuthUrl } from '../api/client';
import './Layout.css';

// ─── Spec-exact colors ────────────────────────────────────────────────────────
const RAIL_W = 220;
const TEAL   = '#2dd4bf';
const MUTED  = '#8b949e';
const TEXT   = '#e6edf3';
const BG     = '#0d1117';
const BORD   = '#30363d';

// ─── Nav definition ───────────────────────────────────────────────────────────
// strategy: if set, calls setActiveStrategy(strategy) on click
// matchFn: determines "active" state from current pathname
const NAV_ITEMS = [
  {
    label:   'Dashboard',
    path:    '/dashboard',
    matchFn: (p) => p === '/dashboard' || p === '/',
    strategy: null,
  },
  {
    label:   'Security Strategies',
    path:    null, // dynamic — uses activeSymbol
    matchFn: (p) => p.startsWith('/security-strategies'),
    strategy: null,
  },
  {
    label:    'Verticals',
    path:     '/verticals',
    matchFn:  (p) => p === '/verticals',
    strategy: 'verticals',
  },
  {
    label:    'Puts & Calls',
    path:     '/naked-options',
    matchFn:  (p) => p === '/naked-options',
    strategy: 'long-calls',
  },
  {
    label:   'Positions',
    path:    '/positions',
    matchFn: (p) => p === '/positions',
    strategy: null,
  },
];

// ─── Main component ───────────────────────────────────────────────────────────

export default function Layout({ setActiveStrategy }) {
  const { fetchPrices, setConfigOpen, activeSymbol } = useApp();
  const location = useLocation();
  const navigate  = useNavigate();

  // ── Schwab status (moved from Header.jsx) ────────────────────────────────
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
    try {
      const authUrl = await getSchwabAuthUrl();
      const popup   = window.open(authUrl, 'schwab-login', 'width=600,height=700,menubar=no,toolbar=no');
      const pollInterval = setInterval(async () => {
        try {
          if (popup?.closed) {
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
        } catch { /* keep polling */ }
      }, 2000);
      setTimeout(() => clearInterval(pollInterval), 5 * 60 * 1000);
    } catch (e) {
      console.error('Schwab auth initiation failed:', e);
    }
  };

  // ── Sync activeStrategy with current route on load/navigation ────────────
  // Ensures OptionsTerminal gets the right config even when the user
  // loads /naked-options or /verticals directly (e.g., bookmark).
  useEffect(() => {
    if (location.pathname === '/naked-options') setActiveStrategy?.('long-calls');
    else if (location.pathname === '/verticals')    setActiveStrategy?.('verticals');
  }, [location.pathname, setActiveStrategy]);

  // ── Watchlist toggle ──────────────────────────────────────────────────────
  const [watchlistOpen, setWatchlistOpen] = useState(() => {
    const saved = localStorage.getItem('watchlist_open');
    return saved === null ? true : saved === 'true';
  });

  useEffect(() => {
    localStorage.setItem('watchlist_open', String(watchlistOpen));
  }, [watchlistOpen]);

  // ── Nav click handler ─────────────────────────────────────────────────────
  const handleNavClick = (item) => {
    if (item.strategy) setActiveStrategy?.(item.strategy);
    if (item.label === 'Security Strategies') {
      navigate(activeSymbol
        ? `/security-strategies/${activeSymbol}`
        : '/security-strategies'
      );
    } else {
      navigate(item.path);
    }
  };

  // ── Shared button hover helpers ───────────────────────────────────────────
  const onHoverIn  = (e) => { e.currentTarget.style.color = TEXT; };
  const onHoverOut = (e) => { e.currentTarget.style.color = MUTED; };

  // ─────────────────────────────────────────────────────────────────────────
  // RENDER
  // ─────────────────────────────────────────────────────────────────────────
  return (
    <div style={{ display: 'flex', minHeight: '100vh', backgroundColor: BG }}>

      {/* ── Left Rail ──────────────────────────────────────────────────── */}
      <nav style={{
        width: RAIL_W, minWidth: RAIL_W,
        height: '100vh', position: 'fixed', top: 0, left: 0,
        backgroundColor: BG, borderRight: `1px solid ${BORD}`,
        display: 'flex', flexDirection: 'column',
        zIndex: 100, overflowY: 'auto',
      }}>

        {/* Logo */}
        <div
          onClick={() => navigate('/dashboard')}
          style={{
            padding: '16px 16px 14px', cursor: 'pointer',
            display: 'flex', alignItems: 'center', gap: 8, flexShrink: 0,
          }}
        >
          <span style={{ color: TEAL, display: 'flex', alignItems: 'center' }}>
            <Logo size={22} />
          </span>
          <span style={{
            color: TEAL, fontFamily: 'monospace', fontSize: 13,
            fontWeight: 700, letterSpacing: '0.02em',
          }}>
            Options Analyzer
          </span>
        </div>

        <div style={{ height: 1, backgroundColor: BORD, marginBottom: 8, flexShrink: 0 }} />

        {/* Nav items */}
        <div style={{ flex: 1 }}>
          {NAV_ITEMS.map(item => {
            const isActive = item.matchFn(location.pathname);
            return (
              <div
                key={item.label}
                onClick={() => handleNavClick(item)}
                style={{
                  display: 'flex', alignItems: 'center',
                  padding: '10px 16px',
                  fontFamily: 'monospace', fontSize: 12,
                  cursor: 'pointer', userSelect: 'none',
                  color: isActive ? TEAL : MUTED,
                  borderLeft: `3px solid ${isActive ? TEAL : 'transparent'}`,
                  backgroundColor: isActive ? 'rgba(45,212,191,0.08)' : 'transparent',
                  transition: 'background 0.1s, color 0.1s',
                }}
                onMouseEnter={e => {
                  if (!isActive) {
                    e.currentTarget.style.color = TEXT;
                    e.currentTarget.style.backgroundColor = 'rgba(255,255,255,0.04)';
                  }
                }}
                onMouseLeave={e => {
                  if (!isActive) {
                    e.currentTarget.style.color = MUTED;
                    e.currentTarget.style.backgroundColor = 'transparent';
                  }
                }}
              >
                {item.label}
              </div>
            );
          })}
        </div>

        {/* Bottom area */}
        <div style={{ marginTop: 'auto', borderTop: `1px solid ${BORD}`, flexShrink: 0 }}>

          {/* Schwab indicator */}
          <div
            onClick={handleSchwabClick}
            title={
              schwabConnected === null ? 'Checking Schwab connection…' :
              schwabConnected            ? 'Connected to Schwab — live market data active' :
              'Click to connect to Schwab'
            }
            style={{
              display: 'flex', alignItems: 'center', gap: 8,
              padding: '10px 16px',
              cursor: schwabConnected ? 'default' : 'pointer',
            }}
          >
            <div style={{
              width: 8, height: 8, borderRadius: '50%', flexShrink: 0,
              backgroundColor: schwabConnected === null ? '#888'
                : schwabConnected ? '#4ade80' : '#f87171',
              boxShadow: schwabConnected ? '0 0 4px rgba(74,222,128,0.5)' : 'none',
            }} />
            <span style={{ fontSize: 10, color: MUTED }}>
              {schwabConnected === null ? 'Checking…'
                : schwabConnected ? 'Schwab Connected'
                : 'Schwab Disconnected'}
            </span>
          </div>

          {/* Settings */}
          <button
            onClick={() => setConfigOpen(true)}
            style={{
              display: 'flex', alignItems: 'center', gap: 8,
              padding: '8px 16px', background: 'none', border: 'none',
              width: '100%', cursor: 'pointer', fontSize: 11,
              color: MUTED, fontFamily: 'monospace', textAlign: 'left',
            }}
            onMouseEnter={onHoverIn}
            onMouseLeave={onHoverOut}
          >
            <span style={{ fontSize: 14 }}>⚙</span>
            <span>Settings</span>
          </button>

          {/* Sign out */}
          <button
            onClick={() => { localStorage.removeItem('ota_token'); window.location.href = '/login'; }}
            style={{
              display: 'flex', alignItems: 'center', gap: 8,
              padding: '8px 16px', background: 'none', border: 'none',
              width: '100%', cursor: 'pointer', fontSize: 11,
              color: MUTED, fontFamily: 'monospace', textAlign: 'left',
              marginBottom: 8,
            }}
            onMouseEnter={onHoverIn}
            onMouseLeave={onHoverOut}
          >
            Sign out
          </button>
        </div>
      </nav>

      {/* ── Main content area ──────────────────────────────────────────── */}
      <div style={{
        marginLeft: RAIL_W,
        flex: 1,
        minHeight: '100vh',
        overflowX: 'hidden',
        position: 'relative',
      }}>

        {/* Watchlist toggle — top-right of content zone */}
        <div style={{ position: 'absolute', top: 8, right: 16, zIndex: 50 }}>
          <button
            onClick={() => setWatchlistOpen(o => !o)}
            style={{
              background: 'transparent',
              border: `1px solid ${BORD}`,
              color: MUTED,
              padding: '4px 10px',
              borderRadius: 4,
              fontSize: 11,
              fontFamily: 'monospace',
              cursor: 'pointer',
              whiteSpace: 'nowrap',
            }}
          >
            Watchlist {watchlistOpen ? '▼' : '▶'}
          </button>

          {/* Watchlist panel — dropdown from toggle */}
          {watchlistOpen && (
            <div style={{
              position: 'absolute', top: '100%', right: 0, marginTop: 4,
              width: 200,
              backgroundColor: '#161b22',
              border: `1px solid ${BORD}`,
              borderRadius: 6,
              boxShadow: '0 8px 24px rgba(0,0,0,0.4)',
              maxHeight: 'calc(100vh - 80px)',
              overflowY: 'auto',
              zIndex: 51,
            }}>
              <Watchlist />
            </div>
          )}
        </div>

        <main className="main-content">
          <Outlet />
        </main>
      </div>

      <Toast />
      <TradeAgentPanel />
    </div>
  );
}
