/**
 * The four steps of the vendor bid form, in order.
 *
 * Kept apart from <ProgressStepper> so that file exports a component and
 * nothing else. A value export sitting alongside a component drops the module
 * out of Vite's Fast Refresh, turning every edit to the stepper into a full
 * page reload mid-form.
 */
import type { StepIndex } from '../types/portal';

export interface StepperStep {
  index: StepIndex;
  label: string;
  shortLabel: string;
}

export const PORTAL_STEPS: StepperStep[] = [
  { index: 1, label: 'Info & Docs', shortLabel: 'Info' },
  { index: 2, label: 'Pricing', shortLabel: 'Pricing' },
  { index: 3, label: 'Notes & Uploads', shortLabel: 'Notes' },
  { index: 4, label: 'Review & Submit', shortLabel: 'Review' },
];
