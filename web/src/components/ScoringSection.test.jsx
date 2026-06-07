/**
 * ScoringSection — seed test for the scoring-weight-sum ADVISORY invariant (OTA-829).
 *
 * Locks the OTA-790 contract: the sum-to-100% indicator is advisory only. When the
 * enabled weights do not total 100.00% the flag MUST fire, the component MUST NOT
 * throw, and the save path MUST NOT be blocked (a per-row blur still persists via
 * updateJunction). The authoritative rejection lives at preview/Apply, never here.
 *
 * The check is inline in the component (ScoringSection.jsx ~215-221), so this is a
 * DOM/Testing-Library test, not a pure-function test. A follow-up extraction story
 * (advisoryChecks.js) would let this re-point to a pure unit test.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import ScoringSection from './ScoringSection';

// Stable showToast identity (see VerdictBandsSection.test for the why):
// a fresh fn per render churns load()'s deps and re-fires the load.
const { toast } = vi.hoisted(() => ({ toast: vi.fn() }));
vi.mock('./Toast', () => ({ useToast: () => ({ showToast: toast }) }));
vi.mock('../api/client', () => ({
  getStrategyJunctions: vi.fn(),
  getRulesAdmin: vi.fn(),
  createJunction: vi.fn(),
  updateJunction: vi.fn(),
  deleteJunction: vi.fn(),
  createOrResumeDraft: vi.fn(),
}));
import * as client from '../api/client';

// One enabled scoring row at 30% → total 30.00%, off the required 100.00%.
const offSumRows = [{
  junction_id: 'j1', rule_key: 'pop_weight', phase: 'scoring',
  evaluation_order: 1, enabled: true, weight: 0.30,
  parameters: {}, parameter_schema: {},
}];

beforeEach(() => {
  client.getStrategyJunctions.mockResolvedValue(offSumRows);
  client.updateJunction.mockResolvedValue({});
  client.createOrResumeDraft.mockResolvedValue({});
});

describe('ScoringSection — weight-sum advisory invariant (OTA-790)', () => {
  it('flags an off-sum weight set advisorily, renders without throwing, and does NOT block save', async () => {
    render(<ScoringSection strategyKey="steady-paycheck" editable />);

    // 1) Flag fires.
    expect(await screen.findByText(/Advisory — the save still succeeds/i)).toBeInTheDocument();
    // The live total reflects the off-sum (30.00%).
    expect(screen.getByText('Total:').parentElement).toHaveTextContent('30.00%');

    // 2) Save is NOT blocked: the weight field stays editable and a blur persists.
    const weightInput = document.querySelector('input[type="number"]');
    expect(weightInput).not.toBeDisabled();
    fireEvent.blur(weightInput);
    await waitFor(() => expect(client.updateJunction).toHaveBeenCalled());
    // (Reaching here without an exception also proves the component did not throw.)
  });
});
