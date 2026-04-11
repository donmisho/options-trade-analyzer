/**
 * useStartupProgress — 6-step startup state machine.
 *
 * Persists step state to sessionStorage under 'ota_startup_state' so progress
 * survives full page reloads. Uses wall-clock timestamps
 * (Date.now()) so elapsed times remain correct across the reload.
 *
 * After step 6 ('ready') completes:
 *   - Writes final timing summary to 'ota_startup_timing' (OTA-442)
 *   - Removes 'ota_startup_state'
 *
 * Returns:
 *   steps         — array with current status/elapsed/hint per step
 *   activateStep  — mark a step 'active', records its start time
 *   completeStep  — mark a step 'complete', auto-activates next pending step
 *   warnStep      — mark a step 'warning', auto-activates next pending step
 *   errorStep     — mark a step 'error' (terminal — no auto-advance)
 *   reset         — reset all steps to pending, clear sessionStorage
 *   totalElapsed  — seconds since wallClockStart (live, 100ms tick)
 *   isFinalized   — true once 'ready' step is 'complete'
 *   hasError      — true if any step is 'error'
 */

import { useState, useEffect, useRef, useCallback } from 'react';

export const STARTUP_STEP_DEFS = [
  { id: 'init',    label: 'Initializing app' },
  { id: 'auth',    label: 'Authenticating with Microsoft' },
  { id: 'backend', label: 'Connecting to backend' },
  { id: 'session', label: 'Verifying user session' },
  { id: 'schwab',  label: 'Checking Schwab connection' },
  { id: 'ready',   label: 'Ready' },
];

export const SS_STATE_KEY  = 'ota_startup_state';
export const SS_TIMING_KEY = 'ota_startup_timing';

function readSaved() {
  try {
    const raw = sessionStorage.getItem(SS_STATE_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

function makeAllPending() {
  return STARTUP_STEP_DEFS.map(def => ({
    ...def, status: 'pending', elapsed: null, hint: null,
  }));
}

export function useStartupProgress() {
  const saved = readSaved();

  // wallClockStart is preserved across page reloads via sessionStorage
  const wallClockStartRef = useRef(saved?.wallClockStart ?? Date.now());

  // Per-step wall-clock start times — restored from sessionStorage if available
  const stepStartsRef = useRef(saved?.stepStarts ?? {});

  const [steps, setSteps] = useState(() =>
    STARTUP_STEP_DEFS.map(def => {
      const s = saved?.steps?.find(s => s.id === def.id);
      return s
        ? { ...def, status: s.status, elapsed: s.elapsed ?? null, hint: s.hint ?? null }
        : { ...def, status: 'pending', elapsed: null, hint: null };
    })
  );

  const [totalElapsed, setTotalElapsed] = useState(
    saved?.wallClockStart ? (Date.now() - saved.wallClockStart) / 1000 : 0
  );

  const readyStep = steps.find(s => s.id === 'ready');
  const isFinalized = readyStep?.status === 'complete';
  const hasError = steps.some(s => s.status === 'error');

  // Running total elapsed — ticks every 100ms while startup is in progress
  useEffect(() => {
    if (isFinalized || hasError) return;
    const id = setInterval(() => {
      setTotalElapsed((Date.now() - wallClockStartRef.current) / 1000);
    }, 100);
    return () => clearInterval(id);
  }, [isFinalized, hasError]);

  // Write current step state to sessionStorage (for redirect survival)
  const persist = useCallback((updatedSteps) => {
    try {
      sessionStorage.setItem(SS_STATE_KEY, JSON.stringify({
        wallClockStart: wallClockStartRef.current,
        stepStarts: stepStartsRef.current,
        steps: updatedSteps.map(s => ({
          id: s.id, status: s.status, elapsed: s.elapsed, hint: s.hint ?? null,
        })),
      }));
    } catch { /* best-effort */ }
  }, []);

  const activateStep = useCallback((id) => {
    if (!stepStartsRef.current[id]) {
      stepStartsRef.current[id] = Date.now();
    }
    setSteps(prev => {
      const next = prev.map(s => s.id === id ? { ...s, status: 'active' } : s);
      persist(next);
      return next;
    });
  }, [persist]);

  const completeStep = useCallback((id) => {
    const startedAt = stepStartsRef.current[id] ?? wallClockStartRef.current;
    const elapsed = (Date.now() - startedAt) / 1000;

    setSteps(prev => {
      const idx = prev.findIndex(s => s.id === id);
      const next = prev.map((s, i) => {
        if (s.id === id) return { ...s, status: 'complete', elapsed };
        if (i === idx + 1 && s.status === 'pending') {
          // Auto-activate next step and record its start time
          stepStartsRef.current[s.id] = Date.now();
          return { ...s, status: 'active' };
        }
        return s;
      });
      persist(next);
      return next;
    });
  }, [persist]);

  const warnStep = useCallback((id, hint = null) => {
    const startedAt = stepStartsRef.current[id] ?? wallClockStartRef.current;
    const elapsed = (Date.now() - startedAt) / 1000;

    setSteps(prev => {
      const idx = prev.findIndex(s => s.id === id);
      const next = prev.map((s, i) => {
        if (s.id === id) return { ...s, status: 'warning', elapsed, hint };
        if (i === idx + 1 && s.status === 'pending') {
          stepStartsRef.current[s.id] = Date.now();
          return { ...s, status: 'active' };
        }
        return s;
      });
      persist(next);
      return next;
    });
  }, [persist]);

  const errorStep = useCallback((id, hint = null) => {
    const startedAt = stepStartsRef.current[id] ?? wallClockStartRef.current;
    const elapsed = (Date.now() - startedAt) / 1000;

    setSteps(prev => {
      const next = prev.map(s =>
        s.id === id ? { ...s, status: 'error', elapsed, hint } : s
      );
      persist(next);
      return next;
    });
  }, [persist]);

  const reset = useCallback(() => {
    try {
      sessionStorage.removeItem(SS_STATE_KEY);
    } catch { /* best-effort */ }
    wallClockStartRef.current = Date.now();
    stepStartsRef.current = {};
    setSteps(makeAllPending());
    setTotalElapsed(0);
  }, []);

  // OTA-442: When ready step completes, output timing and clean up state key
  useEffect(() => {
    if (!isFinalized) return;

    const total = (Date.now() - wallClockStartRef.current) / 1000;
    const timingData = {
      timestamp: new Date().toISOString(),
      total_seconds: parseFloat(total.toFixed(1)),
      steps: steps.map(s => ({
        name: s.label,
        duration_seconds: s.elapsed !== null ? parseFloat(s.elapsed.toFixed(1)) : 0,
        status: s.status,
      })),
    };

    console.log('%cOTA Startup Timing', 'font-weight:bold;font-size:14px;color:#2dd4bf');
    console.log('─'.repeat(44));
    steps.forEach(s => {
      const dur = s.elapsed !== null ? `${parseFloat(s.elapsed.toFixed(1))}s` : '—';
      const icon = s.status === 'complete' ? '✓' : s.status === 'warning' ? '⚠' : '○';
      console.log(`${icon}  ${s.label.padEnd(32)} ${dur}`);
    });
    console.log('─'.repeat(44));
    console.log(`   ${'Total'.padEnd(33)} ${total.toFixed(1)}s`);

    try {
      sessionStorage.setItem(SS_TIMING_KEY, JSON.stringify(timingData));
      sessionStorage.removeItem(SS_STATE_KEY);
    } catch { /* best-effort */ }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isFinalized]);

  return {
    steps,
    activateStep,
    completeStep,
    warnStep,
    errorStep,
    reset,
    totalElapsed,
    isFinalized,
    hasError,
  };
}
