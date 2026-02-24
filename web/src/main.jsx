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
import './styles/global.css';

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <App />
  </StrictMode>
);
