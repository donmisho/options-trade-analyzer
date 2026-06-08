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

// ── OTA-793: behavior + format on top of the OTA-829 advisory seed ──
describe('ScoringSection — behavior & format (OTA-793)', () => {
  it('opens the shared catalog filtered to the scoring phase', async () => {
    const onOpenCatalog = vi.fn();
    render(<ScoringSection strategyKey="steady-paycheck" editable onOpenCatalog={onOpenCatalog} />);
    await screen.findByText('Pop Weight');

    fireEvent.click(screen.getByText('+ Add scoring criterion from catalog'));
    expect(onOpenCatalog).toHaveBeenCalledWith('scoring');
  });

  it('removes a criterion on the draft (delete targets `<key>__draft`)', async () => {
    client.deleteJunction.mockResolvedValue({});
    render(<ScoringSection strategyKey="steady-paycheck" editable />);
    await screen.findByText('Pop Weight');

    fireEvent.click(screen.getByText('Remove'));
    await waitFor(() => expect(client.deleteJunction).toHaveBeenCalled());
    expect(client.deleteJunction).toHaveBeenCalledWith('steady-paycheck__draft', 'pop_weight');
  });

  it('totals a unity weight set as 100.00% with no advisory flag', async () => {
    client.getStrategyJunctions.mockResolvedValue([
      { junction_id: 's1', rule_key: 'pop_weight', phase: 'scoring', evaluation_order: 1,
        enabled: true, weight: 0.6, parameters: {}, parameter_schema: {} },
      { junction_id: 's2', rule_key: 'iv_weight', phase: 'scoring', evaluation_order: 2,
        enabled: true, weight: 0.4, parameters: {}, parameter_schema: {} },
    ]);
    render(<ScoringSection strategyKey="steady-paycheck" editable />);
    await screen.findByText('Pop Weight');

    // Total formatted ##.00% and clean (no off-sum advisory copy).
    expect(screen.getByText('100.00%')).toBeInTheDocument();
    expect(screen.queryByText(/Advisory — the save still succeeds/i)).not.toBeInTheDocument();
  });

  it('is read-only for a shared (non-editable) strategy — no Add, no Remove', async () => {
    render(<ScoringSection strategyKey="health-monitor" editable={false} />);
    await screen.findByText('Pop Weight');
    expect(screen.queryByText('+ Add scoring criterion from catalog')).not.toBeInTheDocument();
    expect(screen.queryByText('Remove')).not.toBeInTheDocument();
  });

  it('carries no `$` (house style)', async () => {
    const { container } = render(<ScoringSection strategyKey="steady-paycheck" editable />);
    await screen.findByText('Pop Weight');
    expect(container.textContent).not.toContain('$');
  });
});
