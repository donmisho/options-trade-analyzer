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

import { useState, useEffect, useCallback, useRef } from 'react';
import { Outlet, useLocation, useNavigate } from 'react-router-dom';
import Logo from '../assets/Logo';
import Toast, { useToast } from './Toast';
import TradeAgentPanel from './TradeAgentPanel';
import SystemVarsPanel from './SystemVarsPanel';
import StartupProgress from './StartupProgress';
import { useApp } from '../context/AppContext';
import { SCORECARD_STRATEGIES } from '../strategy-configs/index';
import { getSchwabStatus, getSchwabAuthUrl, getServicesStatus } from '../api/client';
import { useAuth } from '../context/AuthContext';
import { useStartupProgress, SS_STATE_KEY } from '../hooks/useStartupProgress';
import './Layout.css';

// Base URL for the backend (strips the /api/v1 suffix from the API client base)
const BACKEND_ORIGIN = import.meta.env.VITE_API_BASE_URL || '';

// sessionStorage key — set to 'true' when startup finishes, cleared on logout.
// Prevents the startup sequence from re-running on page reloads within a session.
const STARTUP_DONE_KEY = 'ota_startup_complete';
const isStartupAlreadyDone = () => {
  try { return sessionStorage.getItem(STARTUP_DONE_KEY) === 'true'; } catch { return false; }
};
const markStartupDone = () => {
  try { sessionStorage.setItem(STARTUP_DONE_KEY, 'true'); } catch {}
};

// ─── Spec-exact colors ────────────────────────────────────────────────────────
const RAIL_W = 200;
const TEAL   = '#2dd4bf';
const MUTED  = '#8b949e';
const TEXT   = '#e6edf3';
const BG     = '#0d1117';
const BORD   = '#30363d';

// ─── Nav definition ───────────────────────────────────────────────────────────
// matchFn: determines "active" state from current pathname
const NAV_ITEMS = [
  {
    label:   'Dashboard',
    path:    '/dashboard',
    matchFn: (p) => p === '/dashboard' || p === '/',
  },
  {
    label:   'Security Strategies',
    path:    null, // dynamic — uses activeSymbol
    matchFn: (p) => p.startsWith('/security-strategies'),
  },
  {
    label:   'Trades',
    path:    '/trades',
    matchFn: (p) => p === '/trades' || p.startsWith('/trades?'),
  },
  {
    label:   'Positions',
    path:    '/positions',
    matchFn: (p) => p === '/positions',
  },
];

// ─── Main component ───────────────────────────────────────────────────────────

export default function Layout() {
  const { fetchPrices, activeSymbol, systemVarsPanelOpen, setSystemVarsPanelOpen, strategyAdmin } = useApp();
  const { logout } = useAuth();
  const { showToast } = useToast();
  const location = useLocation();
  const navigate  = useNavigate();

  // ── Startup progress (6-step, hook-driven) ───────────────────────────────
  const {
    steps: startupSteps,
    activateStep,
    completeStep,
    warnStep,
    errorStep,
    reset: resetStartup,
    totalElapsed: startupTotalElapsed,
    hasError: startupHasError,
  } = useStartupProgress();

  const [startupVisible, setStartupVisible] = useState(true);
  // Initialize from sessionStorage — survives page reloads within the same session.
  const [startupComplete, setStartupComplete] = useState(isStartupAlreadyDone);
  const [retryCount, setRetryCount] = useState(0);

  // ── Schwab status (moved from Header.jsx) ────────────────────────────────
  const [schwabConnected, setSchwabConnected] = useState(null);
  const schwabPopupRef = useRef(null);

  // ── Services panel (OTA-500) ─────────────────────────────────────────────
  const [servicesData, setServicesData] = useState([]);
  const [servicesStepActive, setServicesStepActive] = useState(false);
  const [schwabConnecting, setSchwabConnecting] = useState(false);
  const servicesResolveRef = useRef(null);
  const servicesSchwabPopupRef = useRef(null);

  const checkSchwabStatus = useCallback(async () => {
    try {
      const status = await getSchwabStatus();
      setSchwabConnected(status.connected === true);
    } catch {
      setSchwabConnected(false);
    }
  }, []);

  // ── Services panel handlers (OTA-500) ────────────────────────────────────
  const handleServicesConnect = useCallback(async (svc) => {
    if (svc.id !== 'schwab') return;
    if (servicesSchwabPopupRef.current && !servicesSchwabPopupRef.current.closed) {
      servicesSchwabPopupRef.current.focus();
      return;
    }
    setSchwabConnecting(true);
    try {
      const authUrl = await getSchwabAuthUrl();
      const popup = window.open(authUrl, 'schwab-login', 'width=600,height=700,menubar=no,toolbar=no');
      if (!popup || popup.closed) {
        showToast({ type: 'error', message: 'Popup blocked — please allow popups for this site and try again.' });
        setSchwabConnecting(false);
        return;
      }
      servicesSchwabPopupRef.current = popup;
      const pollInterval = setInterval(async () => {
        try {
          if (popup?.closed) {
            clearInterval(pollInterval);
            servicesSchwabPopupRef.current = null;
            setSchwabConnecting(false);
            const st = await getSchwabStatus();
            const connected = st?.connected === true;
            setSchwabConnected(connected);
            setServicesData(prev => prev.map(s => s.id === 'schwab' ? { ...s, connected } : s));
            return;
          }
          const st = await getSchwabStatus();
          if (st?.connected) {
            setSchwabConnected(true);
            setServicesData(prev => prev.map(s => s.id === 'schwab' ? { ...s, connected: true } : s));
            clearInterval(pollInterval);
            servicesSchwabPopupRef.current = null;
            setSchwabConnecting(false);
            if (!popup.closed) popup.close();
          }
        } catch { /* keep polling */ }
      }, 2000);
      setTimeout(() => {
        clearInterval(pollInterval);
        servicesSchwabPopupRef.current = null;
        setSchwabConnecting(false);
      }, 5 * 60 * 1000);
    } catch (e) {
      console.error('Schwab connect failed:', e);
      setSchwabConnecting(false);
    }
  }, [showToast]);

  const handleServicesContinue = useCallback(() => {
    if (servicesResolveRef.current) {
      // Pass current schwabConnected state to the startup sequence
      const connected = servicesData.some(s => s.id === 'schwab' && s.connected);
      servicesResolveRef.current(connected);
      servicesResolveRef.current = null;
    }
  }, [servicesData]);

  // Background 5-minute poll — only after startup completes
  useEffect(() => {
    if (!startupComplete) return;
    const interval = setInterval(checkSchwabStatus, 5 * 60 * 1000);
    return () => clearInterval(interval);
  }, [startupComplete, checkSchwabStatus]);

  // ── Startup sequence ──────────────────────────────────────────────────────
  useEffect(() => {
    let cancelled = false;
    const minDelay = ms => new Promise(r => setTimeout(r, ms));

    const runStartup = async () => {
      // If startup already completed this session, skip entirely.
      if (isStartupAlreadyDone()) { setStartupComplete(true); return; }

      // Determine where to start from — read sessionStorage at the top of each run
      // so retry (which clears sessionStorage) starts fresh
      let savedSteps = [];
      try {
        const raw = sessionStorage.getItem(SS_STATE_KEY);
        savedSteps = raw ? (JSON.parse(raw).steps ?? []) : [];
      } catch { savedSteps = []; }

      const getStatus = id => savedSteps.find(s => s.id === id)?.status ?? 'pending';

      // ── Steps 1–2 (init, auth) ─────────────────────────────────────────
      // On redirect return: already 'complete' in sessionStorage — skip.
      // On fresh load or retry: run them quickly for visual continuity.

      if (getStatus('init') !== 'complete') {
        activateStep('init');
        await minDelay(200);
        if (cancelled) return;
        completeStep('init');      // auto-activates 'auth'
        await minDelay(100);
        if (cancelled) return;
      }

      if (getStatus('auth') !== 'complete') {
        // Fresh load: 'auth' was auto-activated by completeStep('init') above
        await minDelay(300);
        if (cancelled) return;
        completeStep('auth');      // auto-activates 'backend'
      } else {
        // Redirect return: auth already complete — manually activate backend
        // (no completeStep('auth') was called so auto-activate didn't fire)
        activateStep('backend');
      }

      // ── Step 3: Connecting to backend ─────────────────────────────────
      try {
        const [resp] = await Promise.all([
          fetch(`${BACKEND_ORIGIN}/health`, { signal: AbortSignal.timeout(30000) }),
          minDelay(400),
        ]);
        if (cancelled) return;
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        completeStep('backend');   // auto-activates 'session'
      } catch {
        if (cancelled) return;
        errorStep('backend', 'Backend unavailable. Is the server running?');
        return;
      }

      // ── Step 4: Verifying user session ────────────────────────────────
      // Cookie-based auth: session is verified by /auth/me (AuthContext).
      // By the time Layout renders, AuthContext has already confirmed auth.
      if (cancelled) return;
      completeStep('session');   // auto-activates 'services'

      // ── Step 5: Connect External Services ─────────────────────────────
      // Load service registry + live connection state from backend.
      let servicesResult = { services: [] };
      try {
        servicesResult = await getServicesStatus(AbortSignal.timeout(8000));
      } catch { /* use empty list — panel still renders with Continue */ }
      if (cancelled) return;

      const initialSchwab = servicesResult.services?.find(s => s.id === 'schwab');
      const alreadyConnected = initialSchwab?.connected === true;
      const servicesPreviousDone = getStatus('services') === 'complete' || getStatus('services') === 'warning';

      setSchwabConnected(alreadyConnected);

      if (alreadyConnected || servicesPreviousDone) {
        // Schwab already connected (or step was completed on a prior run) — skip the panel.
        completeStep('services');  // auto-activates 'ready'
      } else {
        // Show the interactive panel and wait for the user to click Continue.
        setServicesData(servicesResult.services ?? []);
        setServicesStepActive(true);

        const schwabConnectedOnContinue = await new Promise(resolve => {
          servicesResolveRef.current = resolve;
        });
        if (cancelled) return;
        setServicesStepActive(false);

        if (schwabConnectedOnContinue) {
          completeStep('services');  // auto-activates 'ready'
        } else {
          warnStep('services', 'Schwab not connected — click the indicator in the sidebar to connect.');
        }
      }

      // ── Step 6: Ready ─────────────────────────────────────────────────
      await minDelay(600);
      if (cancelled) return;
      completeStep('ready');
      await minDelay(600);
      if (cancelled) return;

      // Fade out then unmount the startup widget.
      // Write the done flag BEFORE the timeout so any reload within the 310ms
      // fade also sees it and skips startup.
      markStartupDone();
      setStartupVisible(false);
      setTimeout(() => { if (!cancelled) setStartupComplete(true); }, 310);
    };

    runStartup();
    return () => { cancelled = true; };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [retryCount]);

  const handleSchwabClick = async () => {
    if (schwabConnected) return;

    // Fix 5: Focus existing popup if still open
    if (schwabPopupRef.current && !schwabPopupRef.current.closed) {
      schwabPopupRef.current.focus();
      return;
    }

    try {
      const authUrl = await getSchwabAuthUrl();
      const popup   = window.open(authUrl, 'schwab-login', 'width=600,height=700,menubar=no,toolbar=no');

      // Fix 4: Detect popup blocker
      if (!popup || popup.closed) {
        showToast({ type: 'error', message: 'Popup blocked — please allow popups for this site and try again.' });
        return;
      }

      schwabPopupRef.current = popup;

      const pollInterval = setInterval(async () => {
        try {
          if (popup?.closed) {
            clearInterval(pollInterval);
            schwabPopupRef.current = null;
            await checkSchwabStatus();
            return;
          }
          const status = await getSchwabStatus();
          if (status.connected) {
            setSchwabConnected(true);
            clearInterval(pollInterval);
            schwabPopupRef.current = null;
            if (popup && !popup.closed) popup.close();
            fetchPrices();
          }
        } catch { /* keep polling */ }
      }, 2000);
      setTimeout(() => {
        clearInterval(pollInterval);
        schwabPopupRef.current = null;
      }, 5 * 60 * 1000);
    } catch (e) {
      console.error('Schwab auth initiation failed:', e);
    }
  };

  // ── Nav click handler ─────────────────────────────────────────────────────
  const handleNavClick = (item) => {
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
          {/* Section header — static, non-collapsible */}
          <div style={{
            padding: '20px 16px 6px 16px',
            fontFamily: 'monospace', fontSize: 9,
            fontWeight: 700, letterSpacing: '0.6px',
            color: MUTED, textTransform: 'uppercase',
          }}>
            Strategies
          </div>

          {/* Strategy items */}
          {SCORECARD_STRATEGIES.map(strategy => {
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
                  padding: '7px 16px 7px 24px',
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
              width: 6, height: 6, borderRadius: '50%', flexShrink: 0,
              backgroundColor: schwabConnected === null ? '#fbbf24'
                : schwabConnected ? '#4ade80' : '#f87171',
              boxShadow: schwabConnected ? '0 0 4px rgba(74,222,128,0.5)' : 'none',
              animation: schwabConnected === null ? 'ota-pulse 1.2s ease-in-out infinite' : 'none',
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
            onClick={logout}
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

        <main className="main-content">
          {!startupComplete ? (
            <StartupProgress
              steps={startupSteps}
              totalElapsed={startupTotalElapsed}
              visible={startupVisible}
              onRetry={startupHasError ? () => {
                resetStartup();
                setStartupVisible(true);
                setRetryCount(c => c + 1);
              } : null}
            >
              {servicesStepActive && (
                <ServicesPanel
                  services={servicesData}
                  schwabConnecting={schwabConnecting}
                  onConnect={handleServicesConnect}
                  onContinue={handleServicesContinue}
                />
              )}
            </StartupProgress>
          ) : (
            <Outlet />
          )}
        </main>
      </div>

      <Toast />
      <TradeAgentPanel />
      <SystemVarsPanel
        open={systemVarsPanelOpen}
        onClose={() => setSystemVarsPanelOpen(false)}
      />
    </div>
  );
}

// ─── Services Panel ────────────────────────────────────────────────────────────
// Renders inside StartupProgress as children during step 5.

function ServicesPanel({ services, schwabConnecting, onConnect, onContinue }) {
  const schwabConnected = services.some(s => s.id === 'schwab' && s.connected);

  return (
    <div style={{
      marginTop: 8,
      borderTop: '1px solid var(--border)',
      paddingTop: 10,
    }}>
      {services.length === 0 ? (
        <div style={{
          fontSize: 11, color: 'var(--muted)', fontFamily: 'monospace',
          textAlign: 'center', padding: '6px 0',
        }}>
          No external services configured.
        </div>
      ) : services.map(svc => (
        <div key={svc.id} style={{
          display: 'flex', alignItems: 'center', gap: 10, padding: '5px 0',
          opacity: svc.active ? 1 : 0.4,
        }}>
          {/* Status dot */}
          <div style={{
            width: 6, height: 6, borderRadius: '50%', flexShrink: 0,
            backgroundColor: !svc.active ? 'var(--muted)' : svc.connected ? 'var(--green)' : 'var(--red)',
            boxShadow: svc.connected ? '0 0 4px var(--green)' : 'none',
          }} />
          {/* Name + description */}
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontSize: 11, color: 'var(--text)', fontFamily: 'monospace' }}>
              {svc.name}
            </div>
            <div style={{ fontSize: 10, color: 'var(--muted)', fontFamily: 'monospace' }}>
              {svc.description}
            </div>
          </div>
          {/* Connect / status badge */}
          {!svc.active ? (
            <span style={{ fontSize: 10, color: 'var(--muted)', fontFamily: 'monospace', flexShrink: 0 }}>
              Inactive
            </span>
          ) : svc.connected ? (
            <span style={{ fontSize: 10, color: 'var(--green)', fontFamily: 'monospace', flexShrink: 0 }}>
              Connected
            </span>
          ) : svc.auth_type === 'oauth' ? (
            <ServiceConnectButton
              label={schwabConnecting && svc.id === 'schwab' ? 'Connecting…' : 'Connect'}
              disabled={schwabConnecting && svc.id === 'schwab'}
              onClick={() => onConnect(svc)}
            />
          ) : (
            <span style={{ fontSize: 10, color: 'var(--muted)', fontFamily: 'monospace', flexShrink: 0 }}>
              Not connected
            </span>
          )}
        </div>
      ))}

      {/* Continue button — label indicates whether user is skipping Schwab */}
      <div style={{ marginTop: 12, textAlign: 'center' }}>
        <ServiceContinueButton
          label={schwabConnected ? 'Continue' : 'Continue without Schwab'}
          onClick={onContinue}
        />
      </div>
    </div>
  );
}

function ServiceConnectButton({ label, disabled, onClick }) {
  const [hovered, setHovered] = useState(false);
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        padding: '3px 10px',
        background: 'none',
        border: `1px solid ${hovered && !disabled ? 'var(--teal)' : 'var(--muted)'}`,
        borderRadius: 3,
        color: hovered && !disabled ? 'var(--teal)' : 'var(--muted)',
        fontFamily: 'monospace',
        fontSize: 10,
        cursor: disabled ? 'default' : 'pointer',
        flexShrink: 0,
        transition: 'border-color 150ms, color 150ms',
        opacity: disabled ? 0.6 : 1,
      }}
    >
      {label}
    </button>
  );
}

function ServiceContinueButton({ label, onClick }) {
  const [hovered, setHovered] = useState(false);
  return (
    <button
      onClick={onClick}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        padding: '7px 24px',
        background: hovered ? 'rgba(45,212,191,0.1)' : 'none',
        border: `1px solid ${hovered ? 'var(--teal)' : 'var(--border)'}`,
        borderRadius: 4,
        color: hovered ? 'var(--teal)' : 'var(--text)',
        fontFamily: 'monospace',
        fontSize: 12,
        cursor: 'pointer',
        transition: 'border-color 150ms, color 150ms, background 150ms',
      }}
    >
      {label} →
    </button>
  );
}
