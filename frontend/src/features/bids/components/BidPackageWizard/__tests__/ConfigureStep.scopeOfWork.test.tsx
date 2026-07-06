import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { ConfigureStep } from '../ConfigureStep';
import type { Task } from '@/features/tasks/api/task.queries';
import type { WizardData } from '@/features/bids/types';
import { uploadProjectDocument } from '@/features/projects/api/project-documents.mutations';

vi.mock('@/features/bid-templates/hooks/useBidTemplates', () => ({
  useBidTemplates: () => ({
    data: { items: [{ id: 'tpl1', name: 'Grading', trade_id: 'trade1', is_lump_sum: true, item_count: 1 }] },
    isLoading: false,
  }),
}));

vi.mock('@/features/bids/hooks/useProjectDocuments', () => ({
  useProjectDocuments: () => ({ data: [], isLoading: false }),
}));

vi.mock('@/features/projects/api/project-documents.mutations', () => ({
  uploadProjectDocument: vi.fn(),
}));

const task = {
  id: 't1',
  project_id: 'p1',
  trade_id: 'trade1',
  name: 'Mass Grading',
} as unknown as Task;

function buildData(overrides: Partial<WizardData> = {}): WizardData {
  return {
    // Far-future deadline so the deadline check never blocks these tests.
    deadline: '2099-09-01T17:00',
    bidTemplateId: 'tpl1',
    documentIds: [],
    vendorSelections: [],
    instructions: '',
    desiredStartDate: null,
    scopeOfWorkDocumentId: null,
    scopeOfWorkFileName: null,
    ...overrides,
  };
}

function renderStep(opts: {
  data?: WizardData;
  onUpdate?: (p: Partial<WizardData>) => void;
  onNext?: () => void;
} = {}) {
  const onUpdate = opts.onUpdate ?? vi.fn();
  const onNext = opts.onNext ?? vi.fn();
  render(
    <ConfigureStep
      projectId="p1"
      task={task}
      data={opts.data ?? buildData()}
      onUpdate={onUpdate}
      onNext={onNext}
    />,
  );
  return { onUpdate, onNext };
}

describe('ConfigureStep — mandatory Scope of Work', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('blocks Next until a Scope of Work is uploaded', () => {
    const { onNext } = renderStep({ data: buildData({ scopeOfWorkDocumentId: null }) });
    fireEvent.click(screen.getByRole('button', { name: /Next: Select Vendors/i }));
    expect(onNext).not.toHaveBeenCalled();
    expect(screen.getByText(/Scope of Work document is required/i)).toBeInTheDocument();
  });

  it('uploads with document_kind=scope_of_work and stores the returned id', async () => {
    (uploadProjectDocument as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({
      id: 'sow-99',
      file_name: 'scope.pdf',
    });
    const { onUpdate } = renderStep();

    const file = new File(['x'], 'scope.pdf', { type: 'application/pdf' });
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(input, { target: { files: [file] } });

    await waitFor(() => expect(uploadProjectDocument).toHaveBeenCalledTimes(1));
    const formData = (uploadProjectDocument as unknown as ReturnType<typeof vi.fn>).mock.calls[0][1] as FormData;
    expect(formData.get('document_kind')).toBe('scope_of_work');

    await waitFor(() =>
      expect(onUpdate).toHaveBeenCalledWith({
        scopeOfWorkDocumentId: 'sow-99',
        scopeOfWorkFileName: 'scope.pdf',
      }),
    );
  });

  it('allows Next once a Scope of Work is present', () => {
    const { onNext } = renderStep({
      data: buildData({ scopeOfWorkDocumentId: 'sow-1', scopeOfWorkFileName: 'scope.pdf' }),
    });
    fireEvent.click(screen.getByRole('button', { name: /Next: Select Vendors/i }));
    expect(onNext).toHaveBeenCalled();
  });
});
