/**
 * Bid-attachment client-side validation.
 *
 * Step 3 used MIME tokens (application/pdf, image/jpeg, image/png) while every
 * other upload surface uses extension tokens. FileUpload's isAcceptedType
 * demands an exact file.type match for a MIME token, so a vendor's PDF that the
 * browser labelled application/octet-stream was refused in the browser even
 * though the server would have accepted it. The vendor saw no error: the file
 * simply would not attach.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fireEvent, screen, waitFor } from '@testing-library/react';
import { renderWithRouter } from '@/test/test-utils';
import { Step3Documents } from '../Step3Documents';
import { uploadAttachment } from '../../../services/portalApi';
import type { BidFormState } from '../../../types/portal';

vi.mock('../../../services/portalApi', () => ({
  uploadAttachment: vi.fn(),
  deleteAttachment: vi.fn(),
}));

function makeState(): BidFormState {
  return {
    step: 3,
    completedSteps: [1, 2],
    dirty: false,
    companyInfo: { vendor_notes: '', proposed_start_date: null, sow_attested_name: '' },
    pricing: { total_amount: 1000, line_items: [] },
    attachments: [],
    submissionId: 'sub-1',
  };
}

function renderStep() {
  const onAddAttachment = vi.fn();
  renderWithRouter(
    <Step3Documents
      state={makeState()}
      onUpdateNotes={vi.fn()}
      onAddAttachment={onAddAttachment}
      onRemoveAttachment={vi.fn()}
      onNext={vi.fn()}
      onBack={vi.fn()}
      onSaveDraft={vi.fn()}
      ensureSubmissionId={vi.fn().mockResolvedValue('sub-1')}
      onDeadlinePassed={vi.fn()}
    />,
  );
  return { onAddAttachment };
}

function fileInput(): HTMLInputElement {
  const input = document.querySelector<HTMLInputElement>('input[type="file"]');
  if (!input) throw new Error('file input not found');
  return input;
}

function selectFile(
  name: string,
  { type = 'application/octet-stream', sizeBytes }: { type?: string; sizeBytes?: number } = {},
) {
  const file = new File(['data0000'], name, { type });
  if (sizeBytes != null) {
    // jsdom sizes a File by its parts, so an oversize fixture has to be faked.
    Object.defineProperty(file, 'size', { value: sizeBytes });
  }
  fireEvent.change(fileInput(), { target: { files: [file] } });
  return file;
}

describe('Step3Documents: attachment accept list', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    (uploadAttachment as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({
      id: 'att-1',
      name: 'bid.pdf',
      size: 8,
      uploadedAt: '2026-01-01T00:00:00Z',
    });
  });

  it('accepts a PDF the browser typed as application/octet-stream', async () => {
    const { onAddAttachment } = renderStep();

    selectFile('bid.pdf', { type: 'application/octet-stream' });

    await waitFor(() => expect(uploadAttachment).toHaveBeenCalledTimes(1));
    expect(onAddAttachment).toHaveBeenCalled();
    expect(screen.queryByText(/not an accepted file type/i)).not.toBeInTheDocument();
  });

  it('accepts a PDF with a correct application/pdf type', async () => {
    renderStep();

    selectFile('bid.pdf', { type: 'application/pdf' });

    await waitFor(() => expect(uploadAttachment).toHaveBeenCalledTimes(1));
  });

  it('accepts JPEG and PNG regardless of declared type', async () => {
    for (const name of ['photo.jpg', 'photo.jpeg', 'plan.png']) {
      const { unmount } = renderWithRouter(
        <Step3Documents
          state={makeState()}
          onUpdateNotes={vi.fn()}
          onAddAttachment={vi.fn()}
          onRemoveAttachment={vi.fn()}
          onNext={vi.fn()}
          onBack={vi.fn()}
          onSaveDraft={vi.fn()}
          ensureSubmissionId={vi.fn().mockResolvedValue('sub-1')}
          onDeadlinePassed={vi.fn()}
        />,
      );
      selectFile(name, { type: 'application/octet-stream' });
      await waitFor(() => expect(uploadAttachment).toHaveBeenCalled());
      unmount();
      vi.clearAllMocks();
      (uploadAttachment as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({
        id: 'att-1', name, size: 8, uploadedAt: '2026-01-01T00:00:00Z',
      });
    }
  });

  it('still rejects a disallowed extension client-side', async () => {
    renderStep();

    selectFile('malware.exe', { type: 'application/octet-stream' });

    expect(await screen.findByText(/not an accepted file type/i)).toBeInTheDocument();
    expect(uploadAttachment).not.toHaveBeenCalled();
  });

  it('still enforces the 10MB cap', async () => {
    renderStep();

    selectFile('huge.pdf', { type: 'application/pdf', sizeBytes: 11 * 1024 * 1024 });

    expect(await screen.findByText(/exceeds the 10MB limit/i)).toBeInTheDocument();
    expect(uploadAttachment).not.toHaveBeenCalled();
  });
});
