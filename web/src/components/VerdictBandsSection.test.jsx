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
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
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

// ── OTA-793: behavior + format on top of the OTA-829 advisory seed ──
describe('VerdictBandsSection — behavior & format (OTA-793)', () => {
  it('saves the edited band set to the DRAFT key with status preserved', async () => {
    // Draft already present → load() reads it; Save re-reads it to build the PUT.
    client.getAdminStrategies.mockResolvedValue([
      { strategy_key: 'steady-paycheck', verdict_band_set: monotonicBands },
      { strategy_key: 'steady-paycheck__draft', display_name: 'Steady Paycheck',
        consumer_surface: 'screening', description: null,
        compatible_structures: ['bull_put_credit'], verdict_band_set: monotonicBands,
        dte_min: 30, dte_max: 45, status: 'draft' },
    ]);
    render(<VerdictBandsSection strategyKey="steady-paycheck" editable />);

    // Edit band 1's max (stays monotonic — no advisory) → dirty.
    const band1Max = await screen.findByLabelText('Band 1 max score');
    fireEvent.change(band1Max, { target: { value: '95' } });

    fireEvent.click(screen.getByRole('button', { name: /Save bands/i }));
    await waitFor(() => expect(client.updateEngineStrategy).toHaveBeenCalled());

    const [key, body] = client.updateEngineStrategy.mock.calls.at(-1);
    expect(key).toBe('steady-paycheck__draft');     // live is never written here
    expect(body.status).toBe('draft');              // server derives enabled=0
    expect(body.verdict_band_set[0].max_score).toBe(95);
  });

  it('renders read-only bands as ##.00 for a shared strategy — no inputs', async () => {
    render(<VerdictBandsSection strategyKey="steady-paycheck" editable={false} />);

    expect(await screen.findByText('A')).toBeInTheDocument();
    // min – max formatted ##.00 (not bare integers).
    expect(screen.getByText(/70\.00 – 100\.00/)).toBeInTheDocument();
    // No editable inputs in read-only mode.
    expect(screen.queryByLabelText('Band 1 min score')).not.toBeInTheDocument();
    expect(screen.getByText('Shared strategy — read-only')).toBeInTheDocument();
  });

  it('carries no `$` (house style)', async () => {
    const { container } = render(<VerdictBandsSection strategyKey="steady-paycheck" editable={false} />);
    await screen.findByText('A');
    expect(container.textContent).not.toContain('$');
  });
});
