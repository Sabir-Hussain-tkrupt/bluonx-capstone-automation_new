import { describe, it, expect, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { ConfigureStep } from '../ConfigureStep';
import type { Task } from '@/features/tasks/api/task.queries';
import type { WizardData } from '@/features/bids/types';

vi.mock('@/features/bid-templates/hooks/useBidTemplates', () => ({
  useBidTemplates: () => ({ data: { items: [] }, isLoading: false }),
}));

vi.mock('@/features/bids/hooks/useProjectDocuments', () => ({
  useProjectDocuments: () => ({ data: [], isLoading: false }),
}));

const task: Task = {
  id: 't1',
  project_id: 'p1',
  trade_id: 'trade1',
  name: 'Mass Grading',
  phase: 'development',
  bid_type: 'competitive',
  status: 'draft',
  // Cast the rest — ConfigureStep only reads name + trade_id.
} as unknown as Task;

function buildData(overrides: Partial<WizardData> = {}): WizardData {
  return {
    deadline: '2026-09-01T17:00',
    bidTemplateId: null,
    documentIds: [],
    vendorSelections: [],
    instructions: '',
    desiredStartDate: null,
    ...overrides,
  };
}

function renderStep(opts: { data?: WizardData; onUpdate?: (p: Partial<WizardData>) => void } = {}) {
  const onUpdate = opts.onUpdate ?? vi.fn();
  render(
    <ConfigureStep
      projectId="p1"
      task={task}
      data={opts.data ?? buildData()}
      onUpdate={onUpdate}
      onNext={vi.fn()}
    />,
  );
  return { onUpdate };
}

describe('ConfigureStep — desired_start_date picker', () => {
  it('renders a Desired start date input next to the deadline', () => {
    renderStep();
    expect(screen.getByLabelText(/Desired start date/i)).toBeInTheDocument();
  });

  it('is optional (does not block submission when blank)', () => {
    renderStep();
    const input = screen.getByLabelText(/Desired start date/i) as HTMLInputElement;
    expect(input.required).toBe(false);
  });

  it('calls onUpdate with the selected date', () => {
    const { onUpdate } = renderStep();
    const input = screen.getByLabelText(/Desired start date/i) as HTMLInputElement;
    fireEvent.change(input, { target: { value: '2026-10-01' } });
    expect(onUpdate).toHaveBeenCalledWith({ desiredStartDate: '2026-10-01' });
  });
});
