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
import SystemVarsPanel from './SystemVarsPanel';
import { useApp } from '../context/AppContext';
import { SCORECARD_STRATEGIES } from '../strategy-configs/index';
import { getSchwabStatus, getSchwabAuthUrl } from '../api/client';
import { msalInstance } from '../auth/msalConfig';
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
    strategy: 'long_calls',
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
  const { fetchPrices, activeSymbol, systemVarsPanelOpen, setSystemVarsPanelOpen, strategyAdmin } = useApp();
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
    if (location.pathname === '/naked-options') setActiveStrategy?.('long_calls');
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

  // ── Strategies nav section toggle ─────────────────────────────────────────
  const [strategiesNavOpen, setStrategiesNavOpen] = useState(() => {
    const saved = localStorage.getItem('strategiesNavOpen');
    return saved === null ? true : saved === 'true';
  });

  useEffect(() => {
    localStorage.setItem('strategiesNavOpen', String(strategiesNavOpen));
  }, [strategiesNavOpen]);

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
        <div style={{ flexShrink: 0 }}>
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

        {/* Strategies section */}
        <div style={{ flexShrink: 0 }}>
          <div style={{ height: 1, backgroundColor: BORD, margin: '4px 0' }} />
          {/* Section header */}
          <button
            onClick={() => setStrategiesNavOpen(o => !o)}
            style={{
              display: 'flex', alignItems: 'center', justifyContent: 'space-between',
              width: '100%', padding: '8px 16px',
              background: 'none', border: 'none', cursor: 'pointer',
              fontFamily: 'monospace', fontSize: 10,
              fontWeight: 700, letterSpacing: '0.08em',
              color: MUTED, textTransform: 'uppercase',
            }}
          >
            <span>Strategies</span>
            <span style={{ fontSize: 9 }}>{strategiesNavOpen ? '▾' : '▸'}</span>
          </button>

          {/* Strategy items */}
          {strategiesNavOpen && SCORECARD_STRATEGIES.map(strategy => {
            const override = strategyAdmin[strategy.key];
            const isEnabled = override?.enabled ?? strategy.enabled ?? true;
            if (!isEnabled) return null;
            const displayName = override?.name ?? strategy.label;
            const isActive = location.pathname === `/strategies/${strategy.key}`;
            return (
              <div
                key={strategy.key}
                onClick={() => navigate(`/strategies/${strategy.key}`)}
                style={{
                  display: 'flex', alignItems: 'center',
                  padding: '8px 16px 8px 24px',
                  fontFamily: 'monospace', fontSize: 11,
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
                {displayName}
              </div>
            );
          })}
        </div>

        {/* Flex spacer — pushes bottom area to rail bottom */}
        <div style={{ flex: 1 }} />

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
            onClick={() => setSystemVarsPanelOpen(true)}
            title="System Settings"
            aria-label="System Settings"
            style={{
              display: 'flex', alignItems: 'center', gap: 8,
              padding: '8px 16px', background: 'none', border: 'none',
              width: '100%', cursor: 'pointer', fontSize: 11,
              color: MUTED, fontFamily: 'monospace', textAlign: 'left',
              transition: 'color 150ms ease',
            }}
            onMouseEnter={onHoverIn}
            onMouseLeave={onHoverOut}
          >
            <span style={{ fontSize: 14 }}>⚙</span>
            <span>Settings</span>
          </button>

          {/* Sign out */}
          <button
            onClick={() => {
              localStorage.removeItem('ota_token');
              // Clear MSAL session state so the next sign-in doesn't find a
              // stale cached account and silently fail.
              try { msalInstance.clearCache(); } catch {}
              window.location.href = '/login';
            }}
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

        {/* Watchlist toggle — visible only on analysis pages, fixed so it always shows */}
        {/\/(verticals|naked-options|security-strategies)/.test(location.pathname) && (
          <button
            onClick={() => setWatchlistOpen(o => !o)}
            style={{
              position: 'fixed',
              top: 8,
              right: watchlistOpen ? 220 : 0,
              zIndex: 95,
              background: '#161b22',
              border: `1px solid ${BORD}`,
              borderRight: watchlistOpen ? `1px solid ${BORD}` : 'none',
              color: MUTED,
              padding: '8px 6px',
              borderRadius: watchlistOpen ? '4px 0 0 4px' : '4px 0 0 4px',
              fontSize: 10,
              fontFamily: 'monospace',
              cursor: 'pointer',
              whiteSpace: 'nowrap',
              transition: 'right 0.15s ease',
            }}
            title={watchlistOpen ? 'Hide Watchlist' : 'Show Watchlist'}
          >
            {watchlistOpen ? '◀' : '▶'}
          </button>
        )}

        <main className="main-content">
          <Outlet />
        </main>
      </div>

      {/* Watchlist panel — fixed right edge overlay, only on analysis pages */}
      {watchlistOpen && /\/(verticals|naked-options|security-strategies)/.test(location.pathname) && (
        <div style={{
          position: 'fixed',
          top: 0,
          right: 0,
          width: 220,
          height: '100vh',
          backgroundColor: '#161b22',
          borderLeft: `1px solid ${BORD}`,
          zIndex: 90,
          overflowY: 'auto',
          paddingTop: 16,
        }}>
          <Watchlist />
        </div>
      )}

      <Toast />
      <TradeAgentPanel />
      <SystemVarsPanel
        open={systemVarsPanelOpen}
        onClose={() => setSystemVarsPanelOpen(false)}
      />
    </div>
  );
}
