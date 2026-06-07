// Vitest global setup (OTA-829). Registers @testing-library/jest-dom matchers
// (toBeInTheDocument, toBeDisabled, …) and clears the DOM/mocks between tests.
import '@testing-library/jest-dom/vitest';
import { afterEach, vi } from 'vitest';
import { cleanup } from '@testing-library/react';

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});
