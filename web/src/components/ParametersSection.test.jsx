/**
 * ParametersSection — admin-UI tests (OTA-793).
 *
 * Parameters (OTA-827) is an orientation GUIDE, not an editor: per its Phase-0
 * NO-GO finding the v2 prototype's param cards have no net-new backing store, so
 * every former card resolves elsewhere (header DTE, scoring criteria, hard-gate
 * thresholds, exit management). These tests lock the section's contract:
 *   - it renders the four guide rows pointing each card at its real home,
 *   - it states plainly that it is a guide and duplicates nothing, and
 *   - it carries no `$` (house style).
 * No interactions exist to fire (no store, no junction writes), so there is no
 * behavior to assert — that absence IS the contract here.
 */
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import ParametersSection from './ParametersSection';

describe('ParametersSection (OTA-827) — orientation guide', () => {
  it('renders the four parameter-origin guide rows', () => {
    render(<ParametersSection />);
    expect(screen.getByText('Parameters')).toBeInTheDocument();
    expect(screen.getByText('Min DTE · Max DTE')).toBeInTheDocument();
    expect(screen.getByText('Max Short Delta · Min IV Rank')).toBeInTheDocument();
    expect(screen.getByText('Credit % / Debit % of Width')).toBeInTheDocument();
    expect(screen.getByText('Take Profit · Stop Loss')).toBeInTheDocument();
  });

  it('points each former card at its real source of truth (a guide, not a second store)', () => {
    render(<ParametersSection />);
    // Intro disclaims being a store.
    expect(screen.getByText(/this section is a\s+guide, not a second store/i)).toBeInTheDocument();
    // Each row names where the value actually lives.
    expect(screen.getByText(/single source of truth \(DTE Range\)/i)).toBeInTheDocument();
    expect(screen.getByText(/Scored, not gated/i)).toBeInTheDocument();
    expect(screen.getByText(/Hard-gate thresholds/i)).toBeInTheDocument();
    expect(screen.getByText(/Exit-management settings/i)).toBeInTheDocument();
  });

  it('renders no `$` monetary prefix (house style)', () => {
    const { container } = render(<ParametersSection />);
    expect(container.textContent).not.toContain('$');
  });
});
