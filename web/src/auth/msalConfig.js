/**
 * MSAL (Microsoft Authentication Library) configuration.
 *
 * VITE_ENTRA_CLIENT_ID and VITE_ENTRA_TENANT_ID are baked in at build time:
 *   - Local dev: set in web/.env.local
 *   - Production: set as GitHub Actions secrets → injected by SWA workflow
 */

import { PublicClientApplication } from '@azure/msal-browser';

export const msalConfig = {
  auth: {
    clientId: import.meta.env.VITE_ENTRA_CLIENT_ID || '',
    authority: `https://login.microsoftonline.com/${import.meta.env.VITE_ENTRA_TENANT_ID || 'common'}`,
    redirectUri: window.location.origin,
  },
  cache: {
    cacheLocation: 'sessionStorage',
    storeAuthStateInCookie: false,
  },
};

export const loginRequest = {
  scopes: ['openid', 'profile', 'email'],
};

// Singleton MSAL instance — imported by App.jsx (MsalProvider) and LoginPage.jsx
export const msalInstance = new PublicClientApplication(msalConfig);
