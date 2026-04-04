/**
 * LoginPage — "Sign in with Microsoft" via MSAL redirect.
 *
 * Flow:
 *  1. User clicks the button → steps 1–2 of StartupProgress are shown
 *  2. Step 1 "Initializing app" completes immediately (~200ms)
 *  3. Step 2 "Authenticating with Microsoft" becomes active
 *  4. Startup state is saved to sessionStorage (survives the redirect)
 *  5. loginRedirect() fires — Microsoft login page takes over
 *  6. On redirect return, main.jsx marks step 2 complete in sessionStorage
 *  7. Layout.jsx reads sessionStorage and continues from step 3 onward
 */

import { useState, useEffect, useRef } from 'react';
import { useMsal } from '@azure/msal-react';
import { loginRequest } from '../auth/msalConfig';
import logoSrc from '../assets/options-analyzer-logo.png';
import StartupProgress from '../components/StartupProgress';
import { STARTUP_STEP_DEFS, SS_STATE_KEY } from '../hooks/useStartupProgress';

const delay = ms => new Promise(r => setTimeout(r, ms));

function makeSteps() {
  return STARTUP_STEP_DEFS.map(def => ({
    ...def, status: 'pending', elapsed: null, hint: null,
  }));
}

export default function LoginPage() {
  const { instance } = useMsal();
  const [showProgress, setShowProgress] = useState(false);
  const [steps, setSteps] = useState(makeSteps);
  const [totalElapsed, setTotalElapsed] = useState(0);
  const [error, setError] = useState(null);
  const wallClockStartRef = useRef(null);
  const timerRef = useRef(null);

  // Clear any stale startup state from a previous login attempt in this tab
  useEffect(() => {
    sessionStorage.removeItem(SS_STATE_KEY);
  }, []);

  // Running total elapsed timer while progress card is shown
  useEffect(() => {
    if (!showProgress) return;
    timerRef.current = setInterval(() => {
      if (wallClockStartRef.current) {
        setTotalElapsed((Date.now() - wallClockStartRef.current) / 1000);
      }
    }, 100);
    return () => clearInterval(timerRef.current);
  }, [showProgress]);

  async function handleSignIn() {
    setError(null);
    wallClockStartRef.current = Date.now();
    setShowProgress(true);

    // Step 1: Initializing app — app is already running, complete quickly
    const initStartMs = Date.now();
    setSteps(prev => prev.map(s => s.id === 'init' ? { ...s, status: 'active' } : s));
    await delay(200);

    const initElapsed = (Date.now() - initStartMs) / 1000;
    const authStartMs = Date.now();

    // Step 1 complete → Step 2 active
    setSteps(prev => prev.map(s => {
      if (s.id === 'init') return { ...s, status: 'complete', elapsed: initElapsed };
      if (s.id === 'auth') return { ...s, status: 'active' };
      return s;
    }));

    // Persist to sessionStorage before redirect — Layout's hook restores this on return
    sessionStorage.setItem(SS_STATE_KEY, JSON.stringify({
      wallClockStart: wallClockStartRef.current,
      stepStarts: {
        init: initStartMs,
        auth: authStartMs,
      },
      steps: [
        { id: 'init',    status: 'complete', elapsed: initElapsed, hint: null },
        { id: 'auth',    status: 'active',   elapsed: null,        hint: null },
        { id: 'backend', status: 'pending',  elapsed: null,        hint: null },
        { id: 'session', status: 'pending',  elapsed: null,        hint: null },
        { id: 'schwab',  status: 'pending',  elapsed: null,        hint: null },
        { id: 'ready',   status: 'pending',  elapsed: null,        hint: null },
      ],
    }));

    try {
      await instance.loginRedirect(loginRequest);
      // Page navigates away — no code runs after this
    } catch (err) {
      clearInterval(timerRef.current);
      setShowProgress(false);
      setError(err.message || 'Sign-in failed. Please try again.');
    }
  }

  // While progress is shown (redirect in flight), render the progress card
  if (showProgress) {
    return (
      <div style={styles.page}>
        <div style={styles.logoWrapper}>
          <img src={logoSrc} alt="Options Analyzer" style={styles.logo} />
        </div>
        <div style={{ width: '100%', maxWidth: 400 }}>
          <StartupProgress
            steps={steps}
            totalElapsed={totalElapsed}
            visible
            onRetry={null}
          />
        </div>
      </div>
    );
  }

  return (
    <div style={styles.page}>
      <div style={styles.logoWrapper}>
        <img src={logoSrc} alt="Options Analyzer" style={styles.logo} />
      </div>

      <div style={styles.card}>
        <p style={styles.subtitle}>Property of TM Technologies, LLC.</p>

        <button onClick={handleSignIn} style={styles.btn}>
          <MicrosoftLogo />
          <span>Sign in with Microsoft</span>
        </button>

        {error && <p style={styles.error}>{error}</p>}
      </div>
    </div>
  );
}

function MicrosoftLogo() {
  return (
    <svg width="20" height="20" viewBox="0 0 21 21" style={{ marginRight: 10, flexShrink: 0 }}>
      <rect x="1" y="1" width="9" height="9" fill="#f25022" />
      <rect x="11" y="1" width="9" height="9" fill="#7fba00" />
      <rect x="1" y="11" width="9" height="9" fill="#00a4ef" />
      <rect x="11" y="11" width="9" height="9" fill="#ffb900" />
    </svg>
  );
}

const styles = {
  page: {
    minHeight: '100vh',
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    background: '#0f1117',
  },
  card: {
    background: '#1a1d27',
    border: '1px solid #2a2d3a',
    borderRadius: 12,
    padding: '40px 40px',
    width: '100%',
    maxWidth: 400,
    textAlign: 'center',
    boxShadow: '0 8px 32px rgba(0,0,0,0.4)',
  },
  subtitle: {
    margin: '0 0 28px',
    fontSize: 13,
    color: '#6b7280',
  },
  logoWrapper: {
    display: 'flex',
    justifyContent: 'center',
    marginBottom: 48,
  },
  logo: {
    width: 960,
    height: 'auto',
    display: 'block',
  },
  btn: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    width: '100%',
    padding: '12px 20px',
    background: '#2a7ae2',
    color: '#fff',
    border: 'none',
    borderRadius: 8,
    fontSize: 15,
    fontWeight: 500,
    cursor: 'pointer',
    transition: 'background 0.15s',
  },
  error: {
    marginTop: 20,
    padding: '10px 14px',
    background: '#2d1a1a',
    border: '1px solid #5a2020',
    borderRadius: 6,
    color: '#f87171',
    fontSize: 13,
    textAlign: 'left',
  },
};
