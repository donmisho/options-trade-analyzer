/**
 * VerdictBandsSection — seed test for the verdict-band monotonicity ADVISORY
 * invariant (OTA-829).
 *
 * Locks the OTA-790 contract: the non-monotonic indicator is advisory only. When a
 * band set's min_score is not strictly descending the flag MUST fire, the component
 * MUST NOT throw, and Save MUST NOT be blocked (the "Save bands" button stays
 * enabled while there are unsaved edits). The authoritative rejection lives at
 * preview/Apply, never here.
 *
 * The check is inline in the component (VerdictBandsSection.jsx ~100-113), so this
 * is a DOM/Testing-Library test, not a pure-function test (see ScoringSection.test).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import VerdictBandsSection from './VerdictBandsSection';

// Stable showToast identity: useToast must not hand back a fresh fn each render,
// or load()'s useCallback dep churns and re-fires load(), clobbering edited state.
const { toast } = vi.hoisted(() => ({ toast: vi.fn() }));
vi.mock('./Toast', () => ({ useToast: () => ({ showToast: toast }) }));
vi.mock('../api/client', () => ({
  getAdminStrategies: vi.fn(),
  updateEngineStrategy: vi.fn(),
  createOrResumeDraft: vi.fn(),
}));
import * as client from '../api/client';

// A monotonic set (min_score strictly descending) — clean on load.
const monotonicBands = [
  { verdict: 'A', min_score: 70, max_score: 100 },
  { verdict: 'B', min_score: 40, max_score: 69 },
  { verdict: 'F', min_score: 0, max_score: 39 },
];

beforeEach(() => {
  client.getAdminStrategies.mockResolvedValue([
    { strategy_key: 'steady-paycheck', verdict_band_set: monotonicBands },
  ]);
  client.updateEngineStrategy.mockResolvedValue({});
  client.createOrResumeDraft.mockResolvedValue({});
});

describe('VerdictBandsSection — monotonicity advisory invariant (OTA-790)', () => {
  it('flags a non-monotonic edit advisorily, renders without throwing, and leaves Save enabled', async () => {
    // No liveBands prop: bands (and their inputs) appear only after load() resolves,
    // so the edit below isn't clobbered by the async load completing afterward.
    render(<VerdictBandsSection strategyKey="steady-paycheck" editable />);

    // Break monotonicity: raise band 2's min above band 1's (80 ≥ 70).
    const band2Min = await screen.findByLabelText('Band 2 min score');
    fireEvent.change(band2Min, { target: { value: '80' } });

    // 1) Flag fires.
    expect(await screen.findByText(/Non-monotonic band set/i)).toBeInTheDocument();

    // 2) Save is NOT blocked: the edit makes it dirty and "Save bands" stays enabled
    //    despite the advisory flag (it is gated only by dirty/saving, never by the flag).
    expect(screen.getByRole('button', { name: /Save bands/i })).not.toBeDisabled();
  });
});
