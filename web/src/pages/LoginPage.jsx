/**
 * LoginPage — "Sign in with Microsoft" via BFF cookie auth.
 *
 * Flow:
 *  1. User clicks the button → full page redirect to /api/v1/auth/login?provider=entra
 *  2. Backend redirects to Entra
 *  3. Entra redirects back to /api/v1/auth/callback
 *  4. Backend sets ota_session cookie and redirects to /dashboard
 *  5. AuthContext detects cookie via /auth/me → renders the app
 */

import logoSrc from '../assets/options-analyzer-logo.png';
import { useAuth } from '../context/AuthContext';

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

export default function LoginPage() {
  const { login } = useAuth();

  return (
    <div style={styles.page}>
      <div style={styles.logoWrapper}>
        <img src={logoSrc} alt="Options Analyzer" style={styles.logo} />
      </div>

      <div style={styles.card}>
        <p style={styles.subtitle}>Property of TM Technologies, LLC.</p>

        <button onClick={() => login('entra')} style={styles.btn}>
          <MicrosoftLogo />
          <span>Sign in with Microsoft</span>
        </button>
      </div>
    </div>
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
};
