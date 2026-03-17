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
import { msalInstance, loginRequest } from './auth/msalConfig';
import { entraLogin, getSchwabStatus } from './api/client';
import './styles/global.css';

// MSAL v5 requires initialize() before the app renders.
// After initialize(), call handleRedirectPromise() to process the auth code
// that Microsoft sends back in the URL after loginRedirect(). We exchange the
// Entra id_token for our app JWT here — before React renders — so that by
// the time routing runs, ota_token is already in localStorage and RequireAuth
// sends the user straight to /connect or /verticals instead of /login.
msalInstance.initialize().then(async () => {
  let redirectToLogin = false;

  try {
    const result = await msalInstance.handleRedirectPromise();

    if (result?.idToken && !localStorage.getItem('ota_token')) {
      const data = await entraLogin(result.idToken);
      localStorage.setItem('ota_token', data.access_token);

      // Determine where to send the user after login
      let targetRoute = '/connect';
      try {
        const schwabStatus = await getSchwabStatus();
        if (schwabStatus.connected) targetRoute = '/dashboard';
      } catch { /* default to /connect */ }

      // MSAL replaces the URL with /login (the redirectStartPage) after processing
      // the auth code. We override it here — before React renders — so BrowserRouter
      // starts at the correct page instead of re-rendering the login screen.
      window.history.replaceState(null, '', targetRoute);

    } else if (!result) {
      // No redirect in progress. If MSAL has cached accounts but we have no app
      // token, the cached account is stale — clear it so the next loginRedirect
      // goes straight to Microsoft without a silent SSO attempt that will fail.
      const accounts = msalInstance.getAllAccounts();
      if (accounts.length > 0 && !localStorage.getItem('ota_token')) {
        console.warn('[MSAL] Stale cached accounts found without app token — clearing MSAL cache.');
        msalInstance.clearCache();
      }
    }
  } catch (err) {
    // handleRedirectPromise failed — stale nonce, expired state, or network error.
    // Clear all MSAL state so the next loginRedirect starts clean, then
    // force the user back through interactive login rather than silently
    // landing on the login screen with broken auth state.
    console.error('[MSAL] Redirect processing failed:', err);
    try { msalInstance.clearCache(); } catch (clearErr) {
      console.warn('[MSAL] Cache clear failed:', clearErr);
    }
    redirectToLogin = true;
  }

  if (redirectToLogin) {
    // Navigate away to interactive login — nothing below this runs.
    await msalInstance.loginRedirect(loginRequest);
    return;
  }

  createRoot(document.getElementById('root')).render(
    <StrictMode>
      <App />
    </StrictMode>
  );
});
