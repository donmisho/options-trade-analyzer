/**
 * Entry point — mounts the React app into the DOM.
 *
 * WHY StrictMode?
 * React.StrictMode runs your components twice during development
 * (not in production) to help catch accidental side effects.
 * It's a free bug-finder — leave it on during development.
 */

import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import App from './App';
import { msalInstance } from './auth/msalConfig';
import { entraLogin, getSchwabStatus } from './api/client';
import './styles/global.css';

// MSAL v5 requires initialize() before the app renders.
// After initialize(), call handleRedirectPromise() to process the auth code
// that Microsoft sends back in the URL after loginRedirect(). We exchange the
// Entra id_token for our app JWT here — before React renders — so that by
// the time routing runs, ota_token is already in localStorage and RequireAuth
// sends the user straight to /connect or /verticals instead of /login.
msalInstance.initialize().then(async () => {
  try {
    const result = await msalInstance.handleRedirectPromise();
    if (result?.idToken && !localStorage.getItem('ota_token')) {
      const data = await entraLogin(result.idToken);
      localStorage.setItem('ota_token', data.access_token);

      // Determine where to send the user after login
      let targetRoute = '/connect';
      try {
        const schwabStatus = await getSchwabStatus();
        if (schwabStatus.connected) targetRoute = '/verticals';
      } catch { /* default to /connect */ }

      // MSAL replaces the URL with /login (the redirectStartPage) after processing
      // the auth code. We override it here — before React renders — so BrowserRouter
      // starts at the correct page instead of re-rendering the login screen.
      window.history.replaceState(null, '', targetRoute);
    }
  } catch (err) {
    console.error('[MSAL] Redirect processing failed:', err);
  }

  createRoot(document.getElementById('root')).render(
    <StrictMode>
      <App />
    </StrictMode>
  );
});
