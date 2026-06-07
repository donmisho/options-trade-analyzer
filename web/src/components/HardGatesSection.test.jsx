/**
 * HardGatesSection — seed test for the evaluation_order collision ADVISORY
 * invariant (OTA-829).
 *
 * Locks the OTA-790 contract: the duplicate-order indicator is advisory only. With
 * two enabled gate rows sharing an evaluation_order the collision flag MUST fire,
 * the component MUST NOT throw, and the save path MUST NOT be blocked (a per-row
 * blur still persists via updateJunction). The authoritative rejection lives at
 * preview/Apply, never here.
 *
 * The check is inline in the component (HardGatesSection.jsx ~213-221), so this is
 * a DOM/Testing-Library test, not a pure-function test (see ScoringSection.test).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import HardGatesSection from './HardGatesSection';

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

// Two enabled gate rows sharing evaluation_order=1 → a collision.
const collidingRows = [
  { junction_id: 'g1', rule_key: 'min_dte', phase: 'gate', evaluation_order: 1,
    enabled: true, stop_if_fail: true, parameters: {}, parameter_schema: {} },
  { junction_id: 'g2', rule_key: 'max_spread', phase: 'gate', evaluation_order: 1,
    enabled: true, stop_if_fail: true, parameters: {}, parameter_schema: {} },
];

beforeEach(() => {
  client.getStrategyJunctions.mockResolvedValue(collidingRows);
  client.updateJunction.mockResolvedValue({});
  client.createOrResumeDraft.mockResolvedValue({});
});

describe('HardGatesSection — evaluation_order collision advisory invariant (OTA-790)', () => {
  it('flags a duplicate order advisorily, renders without throwing, and does NOT block save', async () => {
    render(<HardGatesSection strategyKey="steady-paycheck" editable />);

    // 1) Flag fires.
    expect(await screen.findByText(/Duplicate evaluation order detected/i)).toBeInTheDocument();

    // 2) Save is NOT blocked: the order field stays editable and a blur persists.
    const orderInput = document.querySelector('input[type="number"]');
    expect(orderInput).not.toBeDisabled();
    fireEvent.blur(orderInput);
    await waitFor(() => expect(client.updateJunction).toHaveBeenCalled());
  });
});
