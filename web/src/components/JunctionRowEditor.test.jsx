/**
 * JunctionRowEditor — admin-UI tests (OTA-793).
 *
 * The shared section-editor row (created by OTA-785, reused by OTA-786/787). It is
 * a controlled component: the host owns the working state, `onChange(patch)` is a
 * local per-keystroke update, `onCommit(patch?)` asks the host to persist (number/
 * text fields on blur, toggles immediately), `onRemove()` deletes the binding.
 * These tests lock that interaction contract plus the field type/format rules:
 *   - enabled / boolean-param / stop_if_fail toggles commit immediately;
 *   - number + text fields update locally on change and commit on blur;
 *   - weight renders/edits as a PERCENT while the stored value stays a fraction
 *     (OTA-786): 0.30 ⇒ "30"; typing 45 ⇒ onChange({ weight: 0.45 });
 *   - the parameter editor is schema-driven (number/boolean/text) and shows
 *     "No parameters" for an empty schema;
 *   - read-only disables every control and drops Remove;
 *   - no `$` (house style).
 */
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import JunctionRowEditor from './JunctionRowEditor';

function baseRow(overrides = {}) {
  return {
    junction_id: 'j1', rule_key: 'pop_score', phase: 'scoring',
    evaluation_order: 1, weight: 0.3, score_penalty: 0,
    enabled: true, stop_if_fail: false, tier: 'derived',
    intent: 'Probability of profit', parameters: {}, parameter_schema: {},
    ...overrides,
  };
}

function renderRow(props = {}) {
  const onChange = vi.fn();
  const onCommit = vi.fn();
  const onRemove = vi.fn();
  const view = render(
    <JunctionRowEditor
      junction={baseRow(props.junction)}
      editable={props.editable ?? true}
      onChange={onChange}
      onCommit={onCommit}
      onRemove={onRemove}
      {...props.flags}
    />,
  );
  return { ...view, onChange, onCommit, onRemove };
}

describe('JunctionRowEditor (OTA-785/786/787 shared editor)', () => {
  it('commits the enabled toggle immediately', () => {
    const { onCommit } = renderRow({ flags: { showWeight: true } });
    // enabled=true ⇒ label reads "Disable <rule_key>".
    fireEvent.click(screen.getByLabelText('Disable pop_score'));
    expect(onCommit).toHaveBeenCalledWith({ enabled: false });
  });

  it('edits weight as a percent while emitting the stored fraction (OTA-786)', () => {
    const { onChange } = renderRow({ flags: { showWeight: true, weightAsPercent: true } });
    // 0.30 fraction renders as the percent "30" (no mid-type rounding jank).
    const weight = screen.getByDisplayValue('30');
    fireEvent.change(weight, { target: { value: '45' } });
    expect(onChange).toHaveBeenCalledWith({ weight: 0.45 });
  });

  it('updates evaluation_order locally on change and persists on blur', () => {
    const { onChange, onCommit } = renderRow({ flags: { showEvaluationOrder: true } });
    const order = screen.getByDisplayValue('1');     // evaluation_order
    fireEvent.change(order, { target: { value: '3' } });
    expect(onChange).toHaveBeenCalledWith({ evaluation_order: 3 });
    expect(onCommit).not.toHaveBeenCalled();         // change is local-only…
    fireEvent.blur(order);
    expect(onCommit).toHaveBeenCalled();             // …blur persists
  });

  it('renders a schema-driven number parameter and commits it on blur', () => {
    const { onChange, onCommit } = renderRow({
      junction: {
        parameter_schema: { min_credit_pct: { type: 'number', default: 0.3, label: 'Min Credit Pct', suffix: '%' } },
        parameters: { min_credit_pct: 0.3 },
      },
      flags: { showParameters: true },
    });
    expect(screen.getByText('Min Credit Pct')).toBeInTheDocument();
    const input = screen.getByDisplayValue('0.3');
    fireEvent.change(input, { target: { value: '0.5' } });
    expect(onChange).toHaveBeenCalledWith({ parameters: { min_credit_pct: 0.5 } });
    fireEvent.blur(input);
    expect(onCommit).toHaveBeenCalled();
  });

  it('commits a boolean parameter immediately on toggle', () => {
    const { onChange, onCommit } = renderRow({
      junction: {
        parameter_schema: { require_liquidity: { type: 'boolean', default: false, label: 'Require Liquidity' } },
        parameters: { require_liquidity: false },
      },
      flags: { showParameters: true },
    });
    fireEvent.click(screen.getByLabelText('Require Liquidity'));
    expect(onChange).toHaveBeenCalledWith({ parameters: { require_liquidity: true } });
    expect(onCommit).toHaveBeenCalled();
  });

  it('commits the stop_if_fail toggle immediately (gates)', () => {
    const { onCommit } = renderRow({ flags: { showStopIfFail: true } });
    // stop_if_fail=false ⇒ the "records" label; toggling halts.
    const halt = screen.getByText('records').closest('label').querySelector('input[type="checkbox"]');
    fireEvent.click(halt);
    expect(onCommit).toHaveBeenCalledWith({ stop_if_fail: true });
  });

  it('shows "No parameters" for an empty schema', () => {
    renderRow({ junction: { parameter_schema: {}, parameters: {} }, flags: { showParameters: true } });
    expect(screen.getByText('No parameters')).toBeInTheDocument();
  });

  it('fires onRemove when Remove is clicked', () => {
    const { onRemove } = renderRow({ flags: { showWeight: true } });
    fireEvent.click(screen.getByText('Remove'));
    expect(onRemove).toHaveBeenCalled();
  });

  it('is read-only when not editable — controls disabled, no Remove', () => {
    renderRow({ editable: false, flags: { showWeight: true, weightAsPercent: true } });
    expect(screen.getByLabelText('Disable pop_score')).toBeDisabled();
    expect(screen.getByDisplayValue('30')).toBeDisabled();
    expect(screen.queryByText('Remove')).not.toBeInTheDocument();
  });

  it('carries no `$` (house style)', () => {
    const { container } = renderRow({ flags: { showWeight: true, weightAsPercent: true } });
    expect(container.textContent).not.toContain('$');
  });
});
