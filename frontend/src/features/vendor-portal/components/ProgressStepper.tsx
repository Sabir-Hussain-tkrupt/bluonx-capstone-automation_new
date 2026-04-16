import { cn } from '@/utils/cn';
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

export interface ProgressStepperProps {
  currentStep: StepIndex;
  completedSteps: number[];
  onStepClick?: (step: StepIndex) => void;
}

export function ProgressStepper({
  currentStep,
  completedSteps,
  onStepClick,
}: ProgressStepperProps) {
  const isCompleted = (step: number) => completedSteps.includes(step);
  const isCurrent = (step: number) => step === currentStep;
  const canNavigateTo = (step: number) => isCompleted(step) && step !== currentStep;

  return (
    <nav
      aria-label="Bid submission progress"
      className="rounded-lg border border-secondary-200 bg-white px-4 py-4 shadow-sm sm:px-6"
    >
      <ol className="flex items-start justify-between gap-1 sm:gap-2">
        {PORTAL_STEPS.map((step, idx) => {
          const done = isCompleted(step.index);
          const current = isCurrent(step.index);
          const navigable = canNavigateTo(step.index);
          const circleClasses = cn(
            'flex h-8 w-8 shrink-0 items-center justify-center rounded-full border-2 text-sm font-semibold transition-colors sm:h-9 sm:w-9',
            done && !current && 'border-success-500 bg-success-500 text-white',
            current && 'border-primary-600 bg-primary-600 text-white',
            !done && !current && 'border-secondary-300 bg-white text-secondary-500',
          );
          const labelClasses = cn(
            'mt-2 text-[11px] font-medium sm:text-xs',
            current ? 'text-primary-700' : done ? 'text-success-700' : 'text-secondary-500',
          );
          const connectorClasses = cn(
            'mx-1 mt-4 h-0.5 flex-1 sm:mt-5 sm:mx-2',
            done ? 'bg-success-500' : 'bg-secondary-200',
          );

          const content = (
            <div className="flex flex-col items-center">
              <span className={circleClasses} aria-hidden={current ? undefined : true}>
                {done && !current ? (
                  <svg viewBox="0 0 20 20" fill="currentColor" className="h-4 w-4">
                    <path
                      fillRule="evenodd"
                      d="M16.704 5.29a1 1 0 010 1.42l-8 8a1 1 0 01-1.42 0l-4-4a1 1 0 011.42-1.42L8 12.58l7.29-7.29a1 1 0 011.41 0z"
                      clipRule="evenodd"
                    />
                  </svg>
                ) : (
                  step.index
                )}
              </span>
              <span className={labelClasses}>
                <span className="hidden sm:inline">{step.label}</span>
                <span className="sm:hidden">{step.shortLabel}</span>
              </span>
            </div>
          );

          return (
            <li
              key={step.index}
              className="flex flex-1 items-start"
              aria-current={current ? 'step' : undefined}
            >
              {navigable ? (
                <button
                  type="button"
                  onClick={() => onStepClick?.(step.index)}
                  className="flex flex-col items-center rounded-md focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:outline-none"
                >
                  {content}
                </button>
              ) : (
                <div
                  className="flex flex-col items-center"
                  aria-disabled={!current}
                >
                  {content}
                </div>
              )}
              {idx < PORTAL_STEPS.length - 1 && <div className={connectorClasses} />}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
