/**
 * StrategyAdminPage — admin-UI page-level tests (OTA-793).
 *
 * Scoped to CROSS-COMPONENT WIRING only — the section/editor behavior is carried
 * by the component tests (HardGates/Scoring/Adjustments/VerdictBands/JunctionRow).
 * Here we lock what only the page owns:
 *   - the selector groups OTA (editable) vs Shared (read-only) and drives the
 *     header/section reflection on selection;
 *   - the header full-row Save targets the live key and never sends derived `enabled`;
 *   - Live Preview (OTA-791): Find trades → createOrResumeDraft + previewDraft, and
 *     results render score ##.00 + expiry mm-dd-yyyy (no `$`);
 *   - Apply (OTA-790) → applyDraft; Reset draft → refreshDraftFromLive;
 *   - the pending-restart banner renders only when getConfigStatus says so;
 *   - var(--bg2) appears ONLY on the permitted surfaces (Preview callout + restart
 *     banner) — never on a section card, header, table row, or full-width band.
 *
 * The mocked `../api/client` freezes today's API contract; engine cleanups behind
 * that boundary cannot affect these tests. No test asserts a verdict value.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import StrategyAdminPage from './StrategyAdminPage';

// Stable showToast identity (see VerdictBandsSection.test for the why).
const { toast } = vi.hoisted(() => ({ toast: vi.fn() }));
vi.mock('../components/Toast', () => ({ useToast: () => ({ showToast: toast }) }));
vi.mock('../api/client', () => ({
  getAdminStrategies: vi.fn(),
  updateEngineStrategy: vi.fn(),
  createOrResumeDraft: vi.fn(),
  refreshDraftFromLive: vi.fn(),
  previewDraft: vi.fn(),
  applyDraft: vi.fn(),
  getConfigStatus: vi.fn(),
  getStrategyJunctions: vi.fn(),
  updateJunction: vi.fn(),
  deleteJunction: vi.fn(),
  getRulesAdmin: vi.fn(),
  createJunction: vi.fn(),
}));
import * as client from '../api/client';

// Two OTA-owned (editable) strategies + one SHARED (read-only).
const STRATS = [
  { strategy_key: 'steady-paycheck', display_name: 'Steady Paycheck', owner_app_id: 'OTA',
    consumer_surface: 'screening', description: 'Income engine',
    compatible_structures: ['bull_put_credit'],
    verdict_band_set: [{ verdict: 'EXECUTE', min_score: 70, max_score: 100 }],
    dte_min: 30, dte_max: 45, status: 'active' },
  { strategy_key: 'weekly-grind', display_name: 'Weekly Grind', owner_app_id: 'OTA',
    consumer_surface: 'screening', description: null,
    compatible_structures: ['long_call'], verdict_band_set: [],
    dte_min: 1, dte_max: 7, status: 'active' },
  { strategy_key: 'health-monitor', display_name: 'Health Monitor', owner_app_id: 'SHARED',
    consumer_surface: 'health', description: null,
    compatible_structures: [], verdict_band_set: [],
    dte_min: null, dte_max: null, status: 'active' },
];

const PREVIEW = {
  draft_key: 'steady-paycheck__draft', config_version: 'abcdef123456',
  underlying_price: 100, candidates_evaluated: 5,
  results: [{
    candidate_id: 'c1', symbol: 'AAPL', structure: 'bull_put_credit',
    structure_label: 'Bull Put Credit', strikes: '100/95',
    expiration: '2026-07-18', dte: 41, score: 71, verdict: 'EXECUTE',
  }],
};

beforeEach(() => {
  client.getAdminStrategies.mockResolvedValue(STRATS);
  // No draft yet for any strategy → draftKey reads 404, sections fall back to live (empty).
  client.getStrategyJunctions.mockImplementation((key) =>
    key.endsWith('__draft') ? Promise.reject(new Error('404')) : Promise.resolve([]));
  client.getConfigStatus.mockResolvedValue({ restart_pending: false });
  client.getRulesAdmin.mockResolvedValue([]);
  client.createOrResumeDraft.mockResolvedValue({});
  client.refreshDraftFromLive.mockResolvedValue({});
  client.applyDraft.mockResolvedValue({});
  client.updateEngineStrategy.mockResolvedValue({});
  client.previewDraft.mockResolvedValue(PREVIEW);
});

describe('StrategyAdminPage — selector & header reflection (OTA-784/827)', () => {
  it('groups OTA (editable) vs Shared (read-only) and defaults to the first editable strategy', async () => {
    render(<StrategyAdminPage />);
    // Default selection = first OTA strategy → its name fills the editable header
    // (the form is populated a tick after the row mounts, so wait on the value).
    await screen.findByLabelText('Display name');
    await waitFor(() => expect(screen.getByLabelText('Display name')).toHaveValue('Steady Paycheck'));
    // Selector groups + members.
    expect(screen.getByText('Your Strategies')).toBeInTheDocument();
    expect(screen.getByText('Shared · read-only')).toBeInTheDocument();
    expect(screen.getByText('Weekly Grind')).toBeInTheDocument();   // selector row (OTA)
    expect(screen.getByText('Health Monitor')).toBeInTheDocument(); // selector row (SHARED)
    expect(screen.getByText('RO')).toBeInTheDocument();             // shared read-only marker
  });

  it('reflects a new selection in the header (display name + DTE)', async () => {
    render(<StrategyAdminPage />);
    await screen.findByLabelText('Display name');

    fireEvent.click(screen.getByText('Weekly Grind'));
    await waitFor(() => expect(screen.getByLabelText('Display name')).toHaveValue('Weekly Grind'));
    expect(screen.getByLabelText('DTE min')).toHaveValue(1);
    expect(screen.getByLabelText('DTE max')).toHaveValue(7);
  });

  it('renders a SHARED strategy read-only (header text, no editable name input, no preview)', async () => {
    render(<StrategyAdminPage />);
    await screen.findByLabelText('Display name');

    fireEvent.click(screen.getByText('Health Monitor'));
    // Read-only marker appears (header + verdict-bands both say it).
    expect((await screen.findAllByText('Shared strategy — read-only')).length).toBeGreaterThan(0);
    expect(screen.queryByLabelText('Display name')).not.toBeInTheDocument();   // name is text, not input
    expect(screen.queryByRole('button', { name: /Reset draft/i })).not.toBeInTheDocument(); // no preview panel
  });
});

describe('StrategyAdminPage — header save wiring (OTA-782/783)', () => {
  it('saves a full-row PUT to the LIVE key and never sends derived `enabled`', async () => {
    render(<StrategyAdminPage />);
    const nameInput = await screen.findByLabelText('Display name');

    fireEvent.change(nameInput, { target: { value: 'Steady Paycheck v2' } });
    expect(await screen.findByText('● Unsaved changes')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Save changes' }));
    await waitFor(() => expect(client.updateEngineStrategy).toHaveBeenCalled());

    const [key, body] = client.updateEngineStrategy.mock.calls.at(-1);
    expect(key).toBe('steady-paycheck');                 // live-direct header write
    expect(body.display_name).toBe('Steady Paycheck v2');
    expect(body.consumer_surface).toBe('screening');     // full-row replace preserves untouched fields
    expect(body).not.toHaveProperty('enabled');          // derived server-side from status
  });
});

describe('StrategyAdminPage — live preview, Apply & Reset wiring (OTA-790/791)', () => {
  it('Find trades evaluates the draft and renders score ##.00 + expiry mm-dd-yyyy', async () => {
    render(<StrategyAdminPage />);
    const sym = await screen.findByLabelText('Preview symbol');

    fireEvent.change(sym, { target: { value: 'AAPL' } });
    fireEvent.click(screen.getByRole('button', { name: /Find trades/i }));

    await waitFor(() => expect(client.previewDraft).toHaveBeenCalledWith('steady-paycheck', 'AAPL'));
    expect(client.createOrResumeDraft).toHaveBeenCalledWith('steady-paycheck');
    // Formatting contract: score ##.00, expiry via formatDate → mm-dd-yyyy.
    expect(await screen.findByText('71.00')).toBeInTheDocument();
    expect(screen.getByText('07-18-2026')).toBeInTheDocument();
  });

  it('Apply promotes the draft once a clean preview exists (applyDraft)', async () => {
    render(<StrategyAdminPage />);
    const sym = await screen.findByLabelText('Preview symbol');

    // Apply is gated on a clean preview — disabled until Find trades runs.
    expect(screen.getByRole('button', { name: /Apply changes/i })).toBeDisabled();
    fireEvent.change(sym, { target: { value: 'AAPL' } });
    fireEvent.click(screen.getByRole('button', { name: /Find trades/i }));
    await screen.findByText('71.00');

    const applyBtn = screen.getByRole('button', { name: /Apply changes/i });
    expect(applyBtn).not.toBeDisabled();
    fireEvent.click(applyBtn);
    await waitFor(() => expect(client.applyDraft).toHaveBeenCalledWith('steady-paycheck'));
  });

  it('Reset draft re-clones from live (refreshDraftFromLive)', async () => {
    render(<StrategyAdminPage />);
    const resetBtn = await screen.findByRole('button', { name: /Reset draft/i });
    fireEvent.click(resetBtn);
    await waitFor(() => expect(client.refreshDraftFromLive).toHaveBeenCalledWith('steady-paycheck'));
  });
});

describe('StrategyAdminPage — restart banner & token discipline (OTA-790, UI-GUIDANCE Part 3a)', () => {
  it('shows the pending-restart banner only when getConfigStatus reports it', async () => {
    client.getConfigStatus.mockResolvedValue({ restart_pending: true });
    render(<StrategyAdminPage />);
    expect(await screen.findByRole('status')).toHaveTextContent(/Config changed/i);
  });

  // jsdom keeps var() in the serialized `style` attribute (getAttribute), but does
  // NOT honor a `[style*="var(--bg2"]` substring SELECTOR — so scan attributes.
  const bg2Elements = () =>
    [...document.body.querySelectorAll('*')]
      .filter(el => el.getAttribute('style')?.includes('var(--bg2'));

  it('uses var(--bg2) ONLY on the permitted Preview callout (no banner, editable strategy)', async () => {
    render(<StrategyAdminPage />);
    await screen.findByLabelText('Preview symbol');

    // Exactly one inline-styled element references var(--bg2): the Preview callout.
    const bg2 = bg2Elements();
    expect(bg2.length).toBe(1);
    // …and it is the callout box (it contains the preview symbol input), not a card,
    // header, table row, or full-width band.
    expect(bg2[0].querySelector('[aria-label="Preview symbol"]')).toBeTruthy();
  });

  it('promotes the restart banner to a second permitted var(--bg2) surface', async () => {
    client.getConfigStatus.mockResolvedValue({ restart_pending: true });
    render(<StrategyAdminPage />);
    await screen.findByRole('status');
    await screen.findByLabelText('Preview symbol');

    const bg2 = bg2Elements();
    // Two and only two: the restart banner + the Preview callout.
    expect(bg2.length).toBe(2);
    expect(bg2.some(el => el.getAttribute('role') === 'status')).toBe(true);
  });

  it('renders no `$` across the live preview surface', async () => {
    const { container } = render(<StrategyAdminPage />);
    const sym = await screen.findByLabelText('Preview symbol');
    fireEvent.change(sym, { target: { value: 'AAPL' } });
    fireEvent.click(screen.getByRole('button', { name: /Find trades/i }));
    await screen.findByText('71.00');
    expect(container.textContent).not.toContain('$');
  });
});
