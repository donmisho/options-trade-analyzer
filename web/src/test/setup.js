// Vitest global setup (OTA-829). Registers @testing-library/jest-dom matchers
// (toBeInTheDocument, toBeDisabled, …) and clears the DOM/mocks between tests.
import '@testing-library/jest-dom/vitest';
import { afterEach, vi } from 'vitest';
import { cleanup, configure } from '@testing-library/react';

// OTA-789: raise Testing Library's default async timeout (findBy*/waitFor) from
// 1000ms to 5000ms. This jsdom env is slow on the OneDrive-backed checkout
// (environment setup alone runs several seconds), and under parallel file load
// the 1000ms default flakes legitimate async assertions across the suite.
configure({ asyncUtilTimeout: 5000 });

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});
