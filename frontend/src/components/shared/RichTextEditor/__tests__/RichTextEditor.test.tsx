import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { RichTextEditor, RichTextViewer } from '..';

describe('RichTextEditor', () => {
  it('renders the formatting toolbar and the stored content', async () => {
    render(<RichTextEditor initialContent="<p><strong>Hello</strong> world</p>" onChange={vi.fn()} />);
    for (const name of ['Bold', 'Italic', 'Underline', 'Strikethrough', 'Heading 1', 'Bulleted list', 'Numbered list', 'Link', 'Undo']) {
      expect(await screen.findByRole('button', { name })).toBeInTheDocument();
    }
    expect(await screen.findByText('Hello')).toBeInTheDocument();
  });

  it('viewer renders through the editor schema and drops unknown markup', async () => {
    const { container } = render(
      <RichTextViewer content={'<h2>Title</h2><p>Safe</p><script>window.x=1</script><img src=x onerror="alert(1)">'} />,
    );
    expect(await screen.findByText('Title')).toBeInTheDocument();
    expect(container.querySelector('h2')).not.toBeNull();
    expect(container.querySelector('script')).toBeNull();
    expect(container.querySelector('img')).toBeNull();
    expect(container.querySelector('[contenteditable="true"]')).toBeNull();
  });
});
