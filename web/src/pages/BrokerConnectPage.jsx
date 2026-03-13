/**
 * BrokerConnectPage — shown after first Entra login to connect a brokerage.
 *
 * Presents two provider cards:
 *  - Schwab: live OAuth popup flow → on success navigate to /verticals
 *  - Tradier: grayed out, labeled "Legacy — not in use"
 *
 * Users can skip this screen and go straight to /verticals.
 */

import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { getSchwabAuthUrl, getSchwabStatus } from '../api/client';

export default function BrokerConnectPage() {
  const navigate = useNavigate();
  const [connecting, setConnecting] = useState(false);
  const [error, setError] = useState(null);

  async function handleConnectSchwab() {
    setConnecting(true);
    setError(null);
    try {
      const url = await getSchwabAuthUrl();
      const popup = window.open(url, 'schwab-oauth', 'width=620,height=720,left=200,top=100');

      if (!popup) {
        throw new Error('Popup blocked. Allow popups for this site and try again.');
      }

      // Poll until the OAuth popup closes, then check connection status
      const interval = setInterval(async () => {
        if (popup.closed) {
          clearInterval(interval);
          try {
            const status = await getSchwabStatus();
            if (status.connected) {
              navigate('/dashboard', { replace: true });
            } else {
              setError('Schwab authorization was not completed. Try again.');
            }
          } catch {
            setError('Could not verify Schwab connection status.');
          } finally {
            setConnecting(false);
          }
        }
      }, 800);
    } catch (err) {
      setError(err.message || 'Could not start Schwab authorization.');
      setConnecting(false);
    }
  }

  return (
    <div style={styles.page}>
      <div style={styles.container}>
        <h1 style={styles.title}>Connect a brokerage</h1>
        <p style={styles.subtitle}>
          Link your brokerage account to load live market data and option chains.
        </p>

        <div style={styles.cards}>
          {/* Schwab */}
          <div style={styles.card}>
            <div style={styles.cardHeader}>
              <span style={styles.providerName}>Charles Schwab</span>
              <span style={{ ...styles.badge, background: '#1a3a2a', color: '#4ade80' }}>
                Active
              </span>
            </div>
            <p style={styles.cardDesc}>
              OAuth 2.0 — click Connect to authorize via your Schwab account.
            </p>
            <button
              onClick={handleConnectSchwab}
              disabled={connecting}
              style={{ ...styles.btn, ...(connecting ? styles.btnDisabled : {}) }}
            >
              {connecting ? 'Authorizing…' : 'Connect Schwab'}
            </button>
          </div>

          {/* Tradier — legacy, grayed out */}
          <div style={{ ...styles.card, opacity: 0.4, pointerEvents: 'none' }}>
            <div style={styles.cardHeader}>
              <span style={styles.providerName}>Tradier</span>
              <span style={{ ...styles.badge, background: '#2a2020', color: '#9ca3af' }}>
                Legacy — not in use
              </span>
            </div>
            <p style={styles.cardDesc}>API token-based access. Not used in production.</p>
            <button style={styles.btn} disabled>
              Connect Tradier
            </button>
          </div>
        </div>

        {error && <p style={styles.error}>{error}</p>}

        <button onClick={() => navigate('/dashboard', { replace: true })} style={styles.skip}>
          Skip for now →
        </button>
      </div>
    </div>
  );
}

const styles = {
  page: {
    minHeight: '100vh',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    background: '#0f1117',
    padding: 24,
  },
  container: {
    width: '100%',
    maxWidth: 640,
    textAlign: 'center',
  },
  title: {
    margin: '0 0 8px',
    fontSize: 26,
    fontWeight: 700,
    color: '#e8eaf0',
  },
  subtitle: {
    margin: '0 0 32px',
    fontSize: 15,
    color: '#6b7280',
  },
  cards: {
    display: 'grid',
    gridTemplateColumns: '1fr 1fr',
    gap: 16,
    marginBottom: 24,
  },
  card: {
    background: '#1a1d27',
    border: '1px solid #2a2d3a',
    borderRadius: 12,
    padding: '24px 20px',
    textAlign: 'left',
  },
  cardHeader: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: 8,
  },
  providerName: {
    fontSize: 16,
    fontWeight: 600,
    color: '#e8eaf0',
  },
  badge: {
    fontSize: 11,
    fontWeight: 500,
    padding: '2px 8px',
    borderRadius: 99,
  },
  cardDesc: {
    fontSize: 13,
    color: '#6b7280',
    marginBottom: 20,
    lineHeight: 1.5,
  },
  btn: {
    width: '100%',
    padding: '10px 16px',
    background: '#2a7ae2',
    color: '#fff',
    border: 'none',
    borderRadius: 7,
    fontSize: 14,
    fontWeight: 500,
    cursor: 'pointer',
  },
  btnDisabled: {
    background: '#3a4a6a',
    cursor: 'not-allowed',
  },
  error: {
    padding: '10px 14px',
    background: '#2d1a1a',
    border: '1px solid #5a2020',
    borderRadius: 6,
    color: '#f87171',
    fontSize: 13,
    textAlign: 'left',
    marginBottom: 16,
  },
  skip: {
    background: 'none',
    border: 'none',
    color: '#6b7280',
    fontSize: 14,
    cursor: 'pointer',
    padding: '8px 16px',
  },
};
