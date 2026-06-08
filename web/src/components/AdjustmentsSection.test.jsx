/**
 * AdjustmentsSection — admin-UI tests (OTA-793).
 *
 * Brings the Post-Scoring Adjustments tab (OTA-787) to parity with the other
 * three section seeds (OTA-829) and adds the behavior/format coverage OTA-793
 * owns:
 *   - advisory duplicate-evaluation_order invariant: flags, never throws, never
 *     blocks save (the authoritative reject lives at preview/Apply);
 *   - save-to-draft routing: the first junction write ensures `<key>__draft`
 *     (create-or-resume), then every CRUD targets the draft key — live untouched;
 *   - Add → opens the shared catalog at phase 'adjustment'; Remove → deletes the
 *     binding on the draft;
 *   - read-only render for a shared (non-editable) strategy: no Add, no Remove;
 *   - no `$` (house style).
 *
 * No test asserts a verdict value (functional reframe).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import AdjustmentsSection from './AdjustmentsSection';

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

// Two enabled adjustment rows sharing evaluation_order=2 → a collision.
const collidingRows = [
  { junction_id: 'a1', rule_key: 'trend_penalty', phase: 'adjustment', evaluation_order: 2,
    enabled: true, parameters: {}, parameter_schema: {} },
  { junction_id: 'a2', rule_key: 'liquidity_bonus', phase: 'adjustment', evaluation_order: 2,
    enabled: true, parameters: {}, parameter_schema: {} },
];

// Default: no draft exists yet (draftKey read 404s → fall back to live). This
// exercises the realistic "first edit creates the draft" path.
function liveOnly(rows) {
  return (key) => key.endsWith('__draft')
    ? Promise.reject(new Error('404 no draft'))
    : Promise.resolve(rows);
}

beforeEach(() => {
  client.getStrategyJunctions.mockImplementation(liveOnly(collidingRows));
  client.updateJunction.mockResolvedValue({});
  client.deleteJunction.mockResolvedValue({});
  client.createOrResumeDraft.mockResolvedValue({});
});

describe('AdjustmentsSection (OTA-787)', () => {
  it('flags a duplicate order advisorily, renders without throwing, and does NOT block save', async () => {
    render(<AdjustmentsSection strategyKey="steady-paycheck" editable />);

    // 1) Advisory flag fires.
    expect(await screen.findByText(/Duplicate evaluation order detected/i)).toBeInTheDocument();

    // 2) Save is NOT blocked: the order field stays editable and a blur persists
    //    to the DRAFT (first write ensures the draft via create-or-resume).
    const orderInput = document.querySelector('input[type="number"]');
    expect(orderInput).not.toBeDisabled();
    fireEvent.blur(orderInput);
    await waitFor(() => expect(client.createOrResumeDraft).toHaveBeenCalledWith('steady-paycheck'));
    await waitFor(() => expect(client.updateJunction).toHaveBeenCalled());
    expect(client.updateJunction.mock.calls[0][0]).toBe('steady-paycheck__draft');
  });

  it('opens the shared catalog filtered to the adjustment phase', async () => {
    const onOpenCatalog = vi.fn();
    render(<AdjustmentsSection strategyKey="steady-paycheck" editable onOpenCatalog={onOpenCatalog} />);
    await screen.findByText(/Duplicate evaluation order detected/i);

    fireEvent.click(screen.getByText('+ Add adjustment from catalog'));
    expect(onOpenCatalog).toHaveBeenCalledWith('adjustment');
  });

  it('removes a binding on the draft (delete targets `<key>__draft`)', async () => {
    render(<AdjustmentsSection strategyKey="steady-paycheck" editable />);
    await screen.findByText(/Duplicate evaluation order detected/i);

    fireEvent.click(screen.getAllByText('Remove')[0]);   // first row: trend_penalty
    await waitFor(() => expect(client.deleteJunction).toHaveBeenCalled());
    expect(client.createOrResumeDraft).toHaveBeenCalledWith('steady-paycheck');
    expect(client.deleteJunction).toHaveBeenCalledWith('steady-paycheck__draft', 'trend_penalty');
  });

  it('is read-only for a shared (non-editable) strategy — no Add, no Remove', async () => {
    client.getStrategyJunctions.mockResolvedValue(collidingRows);   // live read only
    render(<AdjustmentsSection strategyKey="health-monitor" editable={false} />);

    // Rows still render (by rule name) but no edit affordances exist.
    expect(await screen.findByText('Trend Penalty')).toBeInTheDocument();
    expect(screen.queryByText('+ Add adjustment from catalog')).not.toBeInTheDocument();
    expect(screen.queryByText('Remove')).not.toBeInTheDocument();
  });

  it('carries no `$` (house style)', async () => {
    const { container } = render(<AdjustmentsSection strategyKey="steady-paycheck" editable />);
    await screen.findByText(/Duplicate evaluation order detected/i);
    expect(container.textContent).not.toContain('$');
  });
});
