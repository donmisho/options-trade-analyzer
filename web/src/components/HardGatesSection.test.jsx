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

// ── OTA-793: behavior + format on top of the OTA-829 advisory seed ──
describe('HardGatesSection — behavior & format (OTA-793)', () => {
  beforeEach(() => {
    client.deleteJunction.mockResolvedValue({});
  });

  it('opens the shared catalog filtered to the gate phase', async () => {
    const onOpenCatalog = vi.fn();
    render(<HardGatesSection strategyKey="steady-paycheck" editable onOpenCatalog={onOpenCatalog} />);
    await screen.findByText(/Duplicate evaluation order detected/i);

    fireEvent.click(screen.getByText('+ Add hard gate from catalog'));
    expect(onOpenCatalog).toHaveBeenCalledWith('gate');
  });

  it('removes a gate on the draft (delete targets `<key>__draft`)', async () => {
    render(<HardGatesSection strategyKey="steady-paycheck" editable />);
    await screen.findByText(/Duplicate evaluation order detected/i);

    fireEvent.click(screen.getAllByText('Remove')[0]);   // first row: min_dte
    await waitFor(() => expect(client.deleteJunction).toHaveBeenCalled());
    expect(client.deleteJunction).toHaveBeenCalledWith('steady-paycheck__draft', 'min_dte');
  });

  it('toggling enabled commits to the draft via updateJunction', async () => {
    render(<HardGatesSection strategyKey="steady-paycheck" editable />);
    await screen.findByText(/Duplicate evaluation order detected/i);

    fireEvent.click(screen.getByLabelText('Disable min_dte'));   // enabled=true ⇒ "Disable …"
    await waitFor(() => expect(client.updateJunction).toHaveBeenCalled());
    const [key, ruleKey, body] = client.updateJunction.mock.calls.at(-1);
    expect(key).toBe('steady-paycheck__draft');
    expect(ruleKey).toBe('min_dte');
    expect(body.enabled).toBe(false);
  });

  it('is read-only for a shared (non-editable) strategy — no Add, no Remove', async () => {
    render(<HardGatesSection strategyKey="health-monitor" editable={false} />);
    await screen.findByText('Min Dte');   // prettified rule_key still renders
    expect(screen.queryByText('+ Add hard gate from catalog')).not.toBeInTheDocument();
    expect(screen.queryByText('Remove')).not.toBeInTheDocument();
  });

  it('carries no `$` (house style)', async () => {
    const { container } = render(<HardGatesSection strategyKey="steady-paycheck" editable />);
    await screen.findByText(/Duplicate evaluation order detected/i);
    expect(container.textContent).not.toContain('$');
  });
});
