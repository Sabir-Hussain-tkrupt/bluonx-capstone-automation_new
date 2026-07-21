import { describe, it, expect, vi } from 'vitest';
import { fireEvent, screen } from '@testing-library/react';
import { renderWithRouter } from '@/test/test-utils';
import { ProjectDocumentUpload } from '../ProjectDocumentUpload';

vi.mock('@/features/projects/hooks/useProjectDocuments', () => ({
  useUploadProjectDocument: () => ({ mutate: vi.fn(), isPending: false }),
}));

function fileInput(): HTMLInputElement {
  return document.querySelector<HTMLInputElement>('input[type="file"]')!;
}

describe('ProjectDocumentUpload file-type validation', () => {
  it('rejects a disallowed type client-side instead of letting it reach the server', () => {
    // The regression: FileUpload only checked size, so a dropped .txt passed
    // client validation and failed only at the backend magic-byte check.
    renderWithRouter(
      <ProjectDocumentUpload projectId="p1" isOpen onClose={() => {}} />,
    );

    const file = new File(['hello'], 'notes.txt', { type: 'text/plain' });
    fireEvent.change(fileInput(), { target: { files: [file] } });

    expect(screen.getByText(/not an accepted file type/i)).toBeInTheDocument();
  });

  it('accepts an allowed type', () => {
    renderWithRouter(
      <ProjectDocumentUpload projectId="p1" isOpen onClose={() => {}} />,
    );

    const file = new File(['%PDF-1.4'], 'plans.pdf', { type: 'application/pdf' });
    fireEvent.change(fileInput(), { target: { files: [file] } });

    expect(screen.queryByText(/not an accepted file type/i)).not.toBeInTheDocument();
    expect(screen.getByText('plans.pdf')).toBeInTheDocument();
  });
});
