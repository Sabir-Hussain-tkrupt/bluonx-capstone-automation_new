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
  function selectFile(name: string, type = 'application/octet-stream') {
    fireEvent.change(fileInput(), {
      target: { files: [new File(['data0000'], name, { type })] },
    });
  }

  it('rejects a disallowed type client-side instead of letting it reach the server', () => {
    renderWithRouter(
      <ProjectDocumentUpload projectId="p1" isOpen onClose={() => {}} />,
    );

    selectFile('malware.exe');

    expect(screen.getByText(/not an accepted file type/i)).toBeInTheDocument();
  });

  it('accepts PDF, CAD, and Office types for projects', () => {
    // .tif and .tiff stay together: the SoW input shipped .tiff without .tif,
    // which made a .tif scope of work unselectable.
    for (const name of [
      'plans.pdf', 'site.dwg', 'spec.docx', 'budget.xlsx', 'notes.txt',
      'survey.tif', 'survey.tiff',
    ]) {
      const { unmount } = renderWithRouter(
        <ProjectDocumentUpload projectId="p1" isOpen onClose={() => {}} />,
      );
      selectFile(name);
      expect(screen.queryByText(/not an accepted file type/i)).not.toBeInTheDocument();
      expect(screen.getByText(name)).toBeInTheDocument();
      unmount();
    }
  });
});
