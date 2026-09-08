import { useCallback, useEffect, useRef, useState } from 'react';

/**
 * Generic auto-save hook.
 *
 * Task 5.1 wires this to a mocked portalApi save function. Task 5.6
 * will swap it for the real POST/PUT draft endpoints — interface stays
 * identical.
 *
 * Behaviour:
 * - Fires `save()` on a fixed interval (default 2 min) if `dirty`.
 * - Fires `save()` on window blur if `dirty`.
 * - Exposes a manual `save()` trigger for step transitions / explicit buttons.
 */

export type AutoSaveStatus = 'idle' | 'saving' | 'saved' | 'error';

export interface UseAutoSaveOptions {
  /** Called when a save should happen. Must resolve on success, reject on failure. */
  onSave: () => Promise<void>;
  /** Is there anything to save right now? */
  dirty: boolean;
  /** Should auto-save run at all? Used to pause during landing / submitted states. */
  enabled?: boolean;
  /** Interval in ms. Default 2 minutes. Shortened in dev where noted. */
  intervalMs?: number;
}

export interface UseAutoSaveResult {
  status: AutoSaveStatus;
  lastSavedAt: Date | null;
  save: () => Promise<void>;
}

// NOTE for Task 5.6: production interval should stay at 120_000.
// For dev verification you can temporarily lower this via the option.
const DEFAULT_INTERVAL_MS = 2 * 60 * 1000;

export function useAutoSave({
  onSave,
  dirty,
  enabled = true,
  intervalMs = DEFAULT_INTERVAL_MS,
}: UseAutoSaveOptions): UseAutoSaveResult {
  const [status, setStatus] = useState<AutoSaveStatus>('idle');
  const [lastSavedAt, setLastSavedAt] = useState<Date | null>(null);

  // Keep refs in sync so the interval + listener callbacks read fresh state.
  const dirtyRef = useRef(dirty);
  const onSaveRef = useRef(onSave);
  const savingRef = useRef(false);
  useEffect(() => {
    dirtyRef.current = dirty;
  }, [dirty]);
  useEffect(() => {
    onSaveRef.current = onSave;
  }, [onSave]);

  const save = useCallback(async () => {
    if (savingRef.current) return;
    if (!dirtyRef.current) return;
    savingRef.current = true;
    setStatus('saving');
    try {
      await onSaveRef.current();
      setStatus('saved');
      setLastSavedAt(new Date());
    } catch (err) {
      console.error('[useAutoSave] save failed', err);
      setStatus('error');
    } finally {
      savingRef.current = false;
    }
  }, []);

  // Interval timer
  useEffect(() => {
    if (!enabled) return;
    const id = setInterval(() => {
      void save();
    }, intervalMs);
    return () => clearInterval(id);
  }, [enabled, intervalMs, save]);

  // Window blur → save
  useEffect(() => {
    if (!enabled) return;
    const onBlur = () => {
      void save();
    };
    window.addEventListener('blur', onBlur);
    return () => window.removeEventListener('blur', onBlur);
  }, [enabled, save]);

  return { status, lastSavedAt, save };
}
