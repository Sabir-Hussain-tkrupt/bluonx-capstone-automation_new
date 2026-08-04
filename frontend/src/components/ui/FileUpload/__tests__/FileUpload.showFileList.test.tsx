import { describe, it, expect, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { FileUpload } from '../FileUpload';

function fileInput(container: HTMLElement): HTMLInputElement {
  const input = container.querySelector('input[type="file"]');
  if (!input) throw new Error('file input not found');
  return input as HTMLInputElement;
}

describe('FileUpload — showFileList', () => {
  it('renders the internal selected-file list by default', () => {
    const onFilesSelected = vi.fn();
    const { container } = render(<FileUpload onFilesSelected={onFilesSelected} />);
    const file = new File(['x'], 'proposal.pdf', { type: 'application/pdf' });
    fireEvent.change(fileInput(container), { target: { files: [file] } });

    expect(onFilesSelected).toHaveBeenCalled();
    expect(screen.getByText('proposal.pdf')).toBeInTheDocument();
  });

  it('hides the internal list when showFileList is false', () => {
    const onFilesSelected = vi.fn();
    const { container } = render(
      <FileUpload onFilesSelected={onFilesSelected} showFileList={false} />,
    );
    const file = new File(['x'], 'proposal.pdf', { type: 'application/pdf' });
    fireEvent.change(fileInput(container), { target: { files: [file] } });

    expect(onFilesSelected).toHaveBeenCalled();
    expect(screen.queryByText('proposal.pdf')).not.toBeInTheDocument();
  });
});
