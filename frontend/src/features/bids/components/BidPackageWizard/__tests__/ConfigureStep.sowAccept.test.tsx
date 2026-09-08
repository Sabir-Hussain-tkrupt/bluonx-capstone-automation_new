/**
 * Scope of Work file-type and size rules.
 *
 * ConfigureStep has two upload affordances for one bucket: the initial upload
 * and the replace. They carried different accept lists (5 extensions vs 15), so
 * a first .dwg scope of work could not be selected at all while replacing an
 * existing SoW with that same file worked. Neither had a size cap. Both now go
 * through the shared FileUpload with the shared project-document list.
 *
 * Kept apart from ConfigureStep.scopeOfWork.test.tsx, which covers the
 * required-SoW gate rather than file validation.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { ConfigureStep } from '../ConfigureStep';
import { PROJECT_DOCUMENT_ACCEPT } from '@/constants/uploads';
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

function renderStep(data: WizardData = buildData()) {
  const onUpdate = vi.fn();
  const utils = render(
    <ConfigureStep
      projectId="p1"
      task={task}
      data={data}
      onUpdate={onUpdate}
      onNext={vi.fn()}
    />,
  );
  return { onUpdate, ...utils };
}

/** The initial-upload state: no SoW chosen yet. */
function renderInitial() {
  return renderStep(buildData({ scopeOfWorkDocumentId: null }));
}

/** The replace state: a SoW exists, so open the replace affordance. */
function renderReplace() {
  const utils = renderStep(
    buildData({ scopeOfWorkDocumentId: 'sow-1', scopeOfWorkFileName: 'scope.pdf' }),
  );
  fireEvent.click(screen.getByRole('button', { name: /^Replace$/i }));
  return utils;
}

function fileInput(): HTMLInputElement {
  const input = document.querySelector<HTMLInputElement>('input[type="file"]');
  if (!input) throw new Error('file input not found');
  return input;
}

function acceptTokens(): string[] {
  return fileInput()
    .getAttribute('accept')!
    .split(',')
    .map((t) => t.trim())
    .sort();
}

function selectFile(name: string, { sizeBytes }: { sizeBytes?: number } = {}) {
  const file = new File(['data0000'], name, { type: 'application/octet-stream' });
  if (sizeBytes != null) {
    // jsdom sizes a File by its parts, so an oversize fixture has to be faked.
    Object.defineProperty(file, 'size', { value: sizeBytes });
  }
  fireEvent.change(fileInput(), { target: { files: [file] } });
}

const OVER_50MB = 51 * 1024 * 1024;

describe('ConfigureStep: Scope of Work accept list', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    (uploadProjectDocument as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({
      id: 'sow-99',
      file_name: 'scope.dwg',
    });
  });

  it('accepts a .dwg on the initial upload', async () => {
    renderInitial();
    expect(acceptTokens()).toContain('.dwg');

    selectFile('scope.dwg');

    await waitFor(() => expect(uploadProjectDocument).toHaveBeenCalledTimes(1));
    expect(screen.queryByText(/not an accepted file type/i)).not.toBeInTheDocument();
  });

  it('offers the identical extension list on both the initial and replace inputs', () => {
    const { unmount } = renderInitial();
    const initial = acceptTokens();
    unmount();

    renderReplace();
    const replace = acceptTokens();

    expect(initial).toEqual(replace);
    expect(initial).toEqual(PROJECT_DOCUMENT_ACCEPT.split(',').map((t) => t.trim()).sort());
  });

  it.each([
    ['initial', renderInitial],
    ['replace', renderReplace],
  ])('enforces the 50MB cap on the %s input', async (_label, mount) => {
    mount();
    selectFile('huge.pdf', { sizeBytes: OVER_50MB });

    expect(await screen.findByText(/exceeds the 50MB limit/i)).toBeInTheDocument();
    expect(uploadProjectDocument).not.toHaveBeenCalled();
  });

  it.each([
    ['initial', renderInitial],
    ['replace', renderReplace],
  ])('accepts both .tif and .tiff on the %s input', async (_label, mount) => {
    for (const name of ['survey.tif', 'survey.tiff']) {
      const { unmount } = mount();
      selectFile(name);
      await waitFor(() => expect(uploadProjectDocument).toHaveBeenCalled());
      expect(screen.queryByText(/not an accepted file type/i)).not.toBeInTheDocument();
      unmount();
      vi.clearAllMocks();
    }
  });

  it.each([
    ['initial', renderInitial],
    ['replace', renderReplace],
  ])('still rejects a disallowed extension on the %s input', async (_label, mount) => {
    mount();
    selectFile('malware.exe');

    expect(await screen.findByText(/not an accepted file type/i)).toBeInTheDocument();
    expect(uploadProjectDocument).not.toHaveBeenCalled();
  });
});
