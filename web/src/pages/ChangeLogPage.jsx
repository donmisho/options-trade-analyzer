/**
 * ChangeLogPage — Deploy history viewer (OTA-602).
 *
 * Displays the deploy_log table in reverse-chronological order.
 * Columns: Deployed At, Environment, Build ID, Commit, Tickets, Notes.
 *
 * Data Isolation Invariant exception: deploy_log is observability data,
 * not user-scoped. The GET endpoint returns all rows.
 */

import { useState, useEffect } from 'react';
import { getChangeLog } from '../api/client';
import { formatDate } from '../utils/formatDate';

const GITHUB_REPO = 'donmisho/options-trade-analyzer';
const JIRA_BASE = 'https://tmtctech-team.atlassian.net/browse';

const TEAL = '#2dd4bf';
const MUTED = '#8b949e';
const TEXT = '#e6edf3';
const BORDER = '#30363d';
const BG3 = '#21262d';

export default function ChangeLogPage() {
  const [entries, setEntries] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const data = await getChangeLog({ limit: 50 });
        if (!cancelled) setEntries(data);
      } catch (err) {
        if (!cancelled) setError(err.message);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, []);

  if (loading) {
    return (
      <div style={{ padding: 24 }}>
        <h1 style={headingStyle}>Change Log</h1>
        <div style={{ color: MUTED, fontFamily: 'monospace', fontSize: 11, textAlign: 'center', padding: 40 }}>
          Loading...
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div style={{ padding: 24 }}>
        <h1 style={headingStyle}>Change Log</h1>
        <div style={{ color: '#f87171', fontFamily: 'monospace', fontSize: 11, textAlign: 'center', padding: 40 }}>
          {error}
        </div>
      </div>
    );
  }

  return (
    <div style={{ padding: 24 }}>
      <h1 style={headingStyle}>Change Log</h1>

      {entries.length === 0 ? (
        <div style={{ color: MUTED, fontFamily: 'monospace', fontSize: 11, textAlign: 'center', padding: 40 }}>
          No deploys recorded yet.
        </div>
      ) : (
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontFamily: 'monospace' }}>
            <thead>
              <tr>
                {['Deployed At', 'Environment', 'Build ID', 'Commit', 'Tickets', 'Notes'].map(h => (
                  <th key={h} style={thStyle}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {entries.map(row => (
                <tr
                  key={row.id}
                  style={{ borderBottom: `1px solid ${BORDER}` }}
                  onMouseEnter={e => { e.currentTarget.style.backgroundColor = 'rgba(45,212,191,0.02)'; }}
                  onMouseLeave={e => { e.currentTarget.style.backgroundColor = 'transparent'; }}
                >
                  <td style={tdStyle}>
                    {formatDate(row.deployed_at, true)}
                  </td>
                  <td style={tdStyle}>
                    <EnvironmentBadge env={row.environment} />
                  </td>
                  <td style={tdStyle}>
                    <a
                      href={`https://github.com/${GITHUB_REPO}/actions/runs/${row.build_id}`}
                      target="_blank"
                      rel="noopener noreferrer"
                      style={linkStyle}
                    >
                      {row.build_id}
                    </a>
                  </td>
                  <td style={tdStyle}>
                    <a
                      href={`https://github.com/${GITHUB_REPO}/commit/${row.commit_sha}`}
                      target="_blank"
                      rel="noopener noreferrer"
                      style={linkStyle}
                    >
                      {row.commit_sha.slice(0, 7)}
                    </a>
                  </td>
                  <td style={tdStyle}>
                    {row.ticket_keys && row.ticket_keys.length > 0
                      ? row.ticket_keys.map((key, i) => (
                          <span key={key}>
                            {i > 0 && ', '}
                            <a
                              href={`${JIRA_BASE}/${key}`}
                              target="_blank"
                              rel="noopener noreferrer"
                              style={linkStyle}
                            >
                              {key}
                            </a>
                          </span>
                        ))
                      : null}
                  </td>
                  <td style={tdStyle}>
                    {row.notes || ''}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function EnvironmentBadge({ env }) {
  const isProd = env === 'prod';
  return (
    <span style={{
      display: 'inline-block',
      padding: '2px 6px',
      borderRadius: 3,
      fontSize: 9,
      fontWeight: 700,
      fontFamily: 'monospace',
      backgroundColor: isProd ? 'rgba(45,212,191,0.15)' : `rgba(139,148,158,0.15)`,
      color: isProd ? TEAL : MUTED,
      border: `1px solid ${isProd ? 'rgba(45,212,191,0.3)' : 'rgba(139,148,158,0.3)'}`,
    }}>
      {env}
    </span>
  );
}

const headingStyle = {
  fontFamily: 'monospace',
  fontSize: 16,
  fontWeight: 700,
  color: TEXT,
  marginBottom: 16,
};

const thStyle = {
  textAlign: 'left',
  padding: '8px 10px',
  fontSize: 10,
  fontWeight: 400,
  fontFamily: 'monospace',
  textTransform: 'uppercase',
  letterSpacing: '0.4px',
  color: MUTED,
  borderBottom: `1px solid ${BORDER}`,
};

const tdStyle = {
  padding: '8px 10px',
  fontSize: 11,
  fontWeight: 400,
  fontFamily: 'monospace',
  color: TEXT,
  verticalAlign: 'top',
};

const linkStyle = {
  color: TEAL,
  textDecoration: 'none',
};
