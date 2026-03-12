/**
 * LoginPage — "Sign in with Microsoft" via MSAL redirect.
 *
 * Flow:
 *  1. User clicks the button → loginRedirect() → full Microsoft login page
 *  2. Microsoft redirects back to the app with ?code=... in the URL
 *  3. main.jsx calls handleRedirectPromise() → exchanges id_token for our JWT
 *  4. main.jsx stores ota_token → React renders → RequireAuth routes to /connect or /verticals
 *
 * LoginPage itself only needs to trigger the redirect. All post-redirect
 * processing happens in main.jsx before React even mounts.
 */

import { useState } from 'react';
import { useMsal } from '@azure/msal-react';
import { loginRequest } from '../auth/msalConfig';
import logoSrc from '../assets/options-analyzer-logo.png';

export default function LoginPage() {
  const { instance } = useMsal();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  async function handleSignIn() {
    setError(null);
    setLoading(true);
    try {
      await instance.loginRedirect(loginRequest);
      // Page navigates away — no code runs after this
    } catch (err) {
      setError(err.message || 'Sign-in failed. Please try again.');
      setLoading(false);
    }
  }

  return (
    <div style={styles.page}>
      <div style={styles.logoWrapper}>
        <img src={logoSrc} alt="Options Analyzer" style={styles.logo} />
      </div>

      <div style={styles.card}>
        <p style={styles.subtitle}>Property of TM Technologies, LLC.</p>

        <button
          onClick={handleSignIn}
          disabled={loading}
          style={{ ...styles.btn, ...(loading ? styles.btnDisabled : {}) }}
        >
          {loading ? (
            <span>Signing in…</span>
          ) : (
            <>
              <MicrosoftLogo />
              <span>Sign in with Microsoft</span>
            </>
          )}
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
  btnDisabled: {
    background: '#3a4a6a',
    cursor: 'not-allowed',
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
