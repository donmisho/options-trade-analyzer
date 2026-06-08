/**
 * RuleCatalogDrawer — acceptance tests for the single shared rule-catalog browser
 * (OTA-789).
 *
 * Locks the ticket's acceptance criteria:
 *   1. Lists the owner-spanning catalog (OTA + SHARED) with the five required
 *      fields (intent, inputs, expected output, phase, formula-registry status).
 *   2. The phase tabs narrow the list (gate / scoring / adjustment).
 *   3. SHARED rules are shown AND selectable for binding (read-only as rules —
 *      this surface only ever creates a junction, never edits engine_rules).
 *   4. Bind PARITY with the inline pickers it replaced: a gate binds with
 *      stop_if_fail=true; a scoring criterion with stop_if_fail=false, weight=0;
 *      next evaluation_order is computed within the rule's phase. onBound fires.
 *   5. A rule already bound in the active phase is dimmed and NOT re-bindable.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import RuleCatalogDrawer from './RuleCatalogDrawer';

const { toast } = vi.hoisted(() => ({ toast: vi.fn() }));
vi.mock('./Toast', () => ({ useToast: () => ({ showToast: toast }) }));
vi.mock('../api/client', () => ({
  getRulesAdmin: vi.fn(),
  getStrategyJunctions: vi.fn(),
  createJunction: vi.fn(),
  createOrResumeDraft: vi.fn(),
}));
import * as client from '../api/client';

// Owner-spanning catalog: OTA + SHARED, across all three phases.
const CATALOG = [
  { rule_id: 1, owner_app_id: 'OTA', rule_key: 'earnings_in_window', phase: 'gate',
    enabled: true, intent: 'Avoid theta-acceleration near earnings',
    referenced_named_values: ['next_earnings_date', 'dte'],
    formula_ref: 'formula:earnings_gate', formula_registered: true, parameter_schema: {} },
  { rule_id: 2, owner_app_id: 'SHARED', rule_key: 'negative_ev', phase: 'gate',
    enabled: true, intent: 'Reject non-positive expected value',
    referenced_named_values: ['expected_value'],
    formula_ref: 'formula:neg_ev', formula_registered: false, parameter_schema: {} },
  { rule_id: 3, owner_app_id: 'OTA', rule_key: 'pop_score', phase: 'scoring',
    enabled: true, intent: 'Probability of profit', referenced_named_values: ['delta'],
    formula_ref: null, formula_registered: null, parameter_schema: {} },
  { rule_id: 4, owner_app_id: 'OTA', rule_key: 'trend_penalty', phase: 'adjustment',
    enabled: true, intent: 'Deduct when SMA pressures the short strike',
    referenced_named_values: ['sma_alignment'], formula_ref: null,
    formula_registered: null, parameter_schema: {} },
];

// One gate already bound to the strategy → its catalog card must dim.
const BOUND = [
  { junction_id: 'j1', rule_key: 'earnings_in_window', phase: 'gate', evaluation_order: 1, enabled: true },
];

beforeEach(() => {
  vi.clearAllMocks();
  client.getRulesAdmin.mockResolvedValue(CATALOG);
  client.getStrategyJunctions.mockResolvedValue(BOUND);
  client.createOrResumeDraft.mockResolvedValue({});
  client.createJunction.mockResolvedValue({});
});

function renderDrawer(props = {}) {
  return render(
    <RuleCatalogDrawer
      strategyKey="steady-paycheck"
      editable
      initialPhase="gate"
      onClose={() => {}}
      onBound={props.onBound || (() => {})}
      {...props}
    />,
  );
}

describe('RuleCatalogDrawer (OTA-789)', () => {
  it('lists OTA + SHARED rules with the five required fields', async () => {
    renderDrawer();

    // OTA and SHARED gate rules both present.
    expect(await screen.findByText('Earnings In Window')).toBeInTheDocument();
    expect(screen.getByText('Negative Ev')).toBeInTheDocument();
    // Owner provenance shown (SHARED rendered read-only). Exact string so the
    // badge is matched, not the header subtitle which also contains the phrase.
    expect(screen.getByText('Shared · read-only')).toBeInTheDocument();
    // Five fields for the SHARED rule: intent, inputs, expected output, phase, formula status.
    expect(screen.getByText('Reject non-positive expected value')).toBeInTheDocument();
    expect(screen.getByText(/expected_value/)).toBeInTheDocument();          // inputs
    expect(screen.getAllByText(/Pass \/ fail gate/).length).toBeGreaterThan(0); // expected output
    expect(screen.getByText('● Formula not registered')).toBeInTheDocument(); // formula status (false)
    expect(screen.getByText('● Formula registered')).toBeInTheDocument();     // formula status (true)
  });

  it('narrows the list by phase tab', async () => {
    renderDrawer();
    await screen.findByText('Earnings In Window');

    // Scoring tab → scoring rule visible, gate rules gone.
    fireEvent.click(screen.getByText('Scoring'));
    expect(await screen.findByText('Pop Score')).toBeInTheDocument();
    expect(screen.queryByText('Earnings In Window')).not.toBeInTheDocument();
    // The no-formula (condition) rule renders its tri-state n/a label.
    expect(screen.getByText(/No formula \(condition rule\)/)).toBeInTheDocument();
  });

  it('binds a SHARED gate rule with stop_if_fail=true and next order within phase', async () => {
    const onBound = vi.fn();
    renderDrawer({ onBound });
    fireEvent.click(await screen.findByText('Negative Ev'));   // SHARED, gate, unbound

    await waitFor(() => expect(client.createJunction).toHaveBeenCalled());
    expect(client.createOrResumeDraft).toHaveBeenCalledWith('steady-paycheck');
    expect(client.createJunction).toHaveBeenCalledWith(expect.objectContaining({
      strategy_key: 'steady-paycheck__draft',
      rule_key: 'negative_ev',
      stop_if_fail: true,
      evaluation_order: 2,   // earnings_in_window holds order 1 in the gate phase
      enabled: true,
    }));
    await waitFor(() => expect(onBound).toHaveBeenCalled());
  });

  it('binds a scoring criterion with stop_if_fail=false and weight=0', async () => {
    renderDrawer();
    await screen.findByText('Earnings In Window');
    fireEvent.click(screen.getByText('Scoring'));
    fireEvent.click(await screen.findByText('Pop Score'));

    await waitFor(() => expect(client.createJunction).toHaveBeenCalled());
    expect(client.createJunction).toHaveBeenCalledWith(expect.objectContaining({
      rule_key: 'pop_score',
      stop_if_fail: false,
      weight: 0,
      evaluation_order: 1,   // no scoring rows bound yet
    }));
  });

  it('binds an adjustment with stop_if_fail=false and no weight', async () => {
    renderDrawer();
    await screen.findByText('Earnings In Window');
    fireEvent.click(screen.getByText('Adjustments'));
    fireEvent.click(await screen.findByText('Trend Penalty'));

    await waitFor(() => expect(client.createJunction).toHaveBeenCalled());
    const body = client.createJunction.mock.calls[0][0];
    expect(body).toEqual(expect.objectContaining({
      rule_key: 'trend_penalty',
      stop_if_fail: false,
      evaluation_order: 1,
    }));
    expect(body).not.toHaveProperty('weight');   // adjustments carry no weight
  });

  it('dims an already-bound rule and does not re-bind it on click', async () => {
    renderDrawer();
    fireEvent.click(await screen.findByText('Earnings In Window'));   // bound → not selectable
    // Give any errant async bind a chance to fire, then assert it did not.
    await waitFor(() => expect(screen.getByText('(in active set)')).toBeInTheDocument());
    expect(client.createJunction).not.toHaveBeenCalled();
  });
});
