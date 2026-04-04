/**
 * Entry point — mounts the React app into the DOM.
 *
 * WHY StrictMode?
 * React.StrictMode runs your components twice during development
 * (not in production) to help catch accidental side effects.
 * It's a free bug-finder — leave it on during development.
 *
 * Auth redirect flow:
 *  1. User clicks sign in → LoginPage saves startup state to sessionStorage, redirects to Microsoft
 *  2. Microsoft redirects back with ?code=... in the URL
 *  3. handleRedirectPromise() exchanges the code → we get an Entra id_token
 *  4. entraLogin() exchanges id_token for our app JWT → stored in localStorage
 *  5. updateStartupStateForAuth() marks step 2 (auth) complete in sessionStorage with elapsed
 *  6. React renders → Layout reads sessionStorage → continues startup from step 3
 */

import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import App from './App';
import { msalInstance, loginRequest } from './auth/msalConfig';
import { entraLogin } from './api/client';
import { SS_STATE_KEY } from './hooks/useStartupProgress';
import './styles/global.css';
import 'react-grid-layout/css/styles.css';
import 'react-resizable/css/styles.css';

/**
 * After entraLogin completes, mark the 'auth' step complete in sessionStorage.
 * Layout's useStartupProgress hook reads this on mount so it can show step 2
 * as already complete (with the correct MSAL redirect elapsed time).
 */
function updateStartupStateForAuth() {
  try {
    const raw = sessionStorage.getItem(SS_STATE_KEY);
    if (!raw) return;
    const saved = JSON.parse(raw);
    const authStartedAt = saved.stepStarts?.auth;
    if (!authStartedAt) return;

    const authElapsed = (Date.now() - authStartedAt) / 1000;
    const updatedSteps = (saved.steps ?? []).map(s =>
      s.id === 'auth' ? { ...s, status: 'complete', elapsed: authElapsed } : s
    );
    sessionStorage.setItem(SS_STATE_KEY, JSON.stringify({
      ...saved,
      steps: updatedSteps,
    }));
  } catch { /* best-effort */ }
}

// MSAL v5 requires initialize() before the app renders.
msalInstance.initialize().then(async () => {
  let redirectToLogin = false;

  try {
    const result = await msalInstance.handleRedirectPromise();

    if (result?.idToken && !localStorage.getItem('ota_token')) {
      const data = await entraLogin(result.idToken);
      localStorage.setItem('ota_token', data.access_token);

      // Mark auth step complete with elapsed time — Layout picks this up
      updateStartupStateForAuth();

      // Always route to dashboard. Layout's startup (step 5) checks Schwab connection.
      window.history.replaceState(null, '', '/dashboard');

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
