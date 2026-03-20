/**
 * DashboardPage — Phase 2.3 Widget Framework
 *
 * Renders a react-grid-layout grid of widgets, one per entry in the user's
 * saved (or default) layout config from GET /api/v1/dashboard.
 *
 * Layout is FIXED in 2.3 (isDraggable=false, isResizable=false).
 * Phase 2.4 enables drag-and-drop by flipping those two props — no other
 * changes required anywhere.
 *
 * Widget rendering is driven entirely by WIDGET_REGISTRY — adding a new
 * widget type = one component + one registry line, nothing else.
 *
 * Layout is cached in localStorage (5-min TTL) to avoid a server round-trip
 * on every page load.
 */

import { useState, useEffect } from 'react';
import { ResponsiveGridLayout } from 'react-grid-layout';
import { useMsal } from '@azure/msal-react';
import { WIDGET_REGISTRY } from '../widgets/WidgetRegistry';
import { getDashboardLayout } from '../api/client';
import { formatDate } from '../utils/formatDate';

const LAYOUT_CACHE_KEY = 'ota_dashboard_layout';
const LAYOUT_CACHE_TTL = 5 * 60 * 1000; // 5 minutes

function getGreeting() {
  const h = new Date().getHours();
  if (h < 12) return 'Good morning';
  if (h < 17) return 'Good afternoon';
  return 'Good evening';
}

function getFirstName(fullName) {
  return fullName ? fullName.split(' ')[0] : 'Don';
}

export default function DashboardPage() {
  const { accounts } = useMsal();
  const name = getFirstName(accounts[0]?.name);

  const [layout, setLayout]   = useState([]);
  const [widgets, setWidgets] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError]     = useState(null);

  useEffect(() => {
    const loadLayout = async () => {
      // Check localStorage cache first
      try {
        const cached = localStorage.getItem(LAYOUT_CACHE_KEY);
        if (cached) {
          const { data, timestamp } = JSON.parse(cached);
          if (Date.now() - timestamp < LAYOUT_CACHE_TTL) {
            setLayout(data.layout);
            setWidgets(data.widgets);
            setLoading(false);
            return;
          }
        }
      } catch (_) { /* ignore corrupt cache */ }

      // Fetch from backend
      try {
        const res = await getDashboardLayout();
        setLayout(res.layout);
        setWidgets(res.widgets);
        localStorage.setItem(LAYOUT_CACHE_KEY, JSON.stringify({
          data: res,
          timestamp: Date.now(),
        }));
      } catch (err) {
        setError('Failed to load dashboard layout.');
        console.error(err);
      } finally {
        setLoading(false);
      }
    };

    loadLayout();
  }, []);

  if (loading) {
    return (
      <div style={{ padding: '2rem', color: '#6b7280' }}>Loading dashboard…</div>
    );
  }

  if (error) {
    return (
      <div style={{ padding: '2rem', color: '#f87171' }}>{error}</div>
    );
  }

  return (
    <div style={s.page}>
      {/* Greeting */}
      <div style={s.welcome}>
        <h1 style={s.greeting}>{getGreeting()}, {name}.</h1>
        <p style={s.date}>{formatDate(new Date())}</p>
      </div>

      {/* Widget Grid */}
      <ResponsiveGridLayout
        className="layout"
        layouts={{ lg: layout }}
        breakpoints={{ lg: 1200, md: 996, sm: 768 }}
        cols={{ lg: 12, md: 10, sm: 6 }}
        rowHeight={80}
        isDraggable={false}
        isResizable={false}
        margin={[12, 12]}
      >
        {widgets.map((widgetConfig) => {
          const WidgetComponent = WIDGET_REGISTRY[widgetConfig.type];
          if (!WidgetComponent) {
            return (
              <div key={widgetConfig.id} style={s.unknownWidget}>
                Unknown widget type: {widgetConfig.type}
              </div>
            );
          }
          return (
            <div key={widgetConfig.id} style={s.widgetOuter}>
              <WidgetComponent config={widgetConfig} isEditMode={false} />
            </div>
          );
        })}
      </ResponsiveGridLayout>
    </div>
  );
}

const s = {
  page: {
    padding: '36px 40px',
    maxWidth: 1400,
    margin: '0 auto',
    color: '#e4e7ef',
  },
  welcome: {
    marginBottom: 32,
    paddingBottom: 24,
    borderBottom: '1px solid #252a3a',
  },
  greeting: {
    margin: 0,
    fontSize: 28,
    fontWeight: 700,
    color: '#e8eaf0',
    letterSpacing: '-0.3px',
  },
  date: {
    margin: '6px 0 0',
    fontSize: 13,
    color: '#6b7280',
  },
  widgetOuter: {
    background: '#14161f',
    border: '1px solid #252a3a',
    borderRadius: 10,
    overflow: 'hidden',
  },
  unknownWidget: {
    padding: '1rem',
    color: '#6b7280',
    fontSize: 13,
  },
};
