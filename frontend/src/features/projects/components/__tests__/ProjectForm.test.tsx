import { describe, it, expect, vi } from 'vitest';
import { fireEvent, screen } from '@testing-library/react';
import userEventBase from '@testing-library/user-event';
import { renderWithRouter } from '@/test/test-utils';
import { ProjectForm } from '../ProjectForm';

const userEvent = userEventBase.setup({ delay: null });

function renderForm() {
  const onSubmit = vi.fn();
  renderWithRouter(<ProjectForm isOpen onClose={() => {}} onSubmit={onSubmit} />);
  const dialog = screen.getByRole('dialog');
  const field = (name: string) => dialog.querySelector<HTMLInputElement>(`input[name="${name}"]`)!;
  return { onSubmit, dialog, field };
}

describe('ProjectForm validation', () => {
  it('rejects a whitespace-only name', async () => {
    // z.string().min(2) alone passes on "  "; the .trim() makes the client
    // reject it up front instead of leaning on a backend 422.
    const { onSubmit, field } = renderForm();

    await userEvent.type(field('name'), '   ');
    await userEvent.click(screen.getByRole('button', { name: 'Create Project' }));

    expect(onSubmit).not.toHaveBeenCalled();
    expect(
      screen.getByText('Project name is required (min 2 characters)'),
    ).toBeInTheDocument();
  });

  it('accepts a zero budget (not treated as empty)', async () => {
    const { onSubmit, field } = renderForm();

    await userEvent.type(field('name'), 'Riverside Grading');
    await userEvent.type(field('budget'), '0');
    await userEvent.click(screen.getByRole('button', { name: 'Create Project' }));

    expect(onSubmit).toHaveBeenCalledWith(
      expect.objectContaining({ name: 'Riverside Grading', budget: 0 }),
    );
  });

  it('rejects an end date before the start date', async () => {
    const { onSubmit, field } = renderForm();

    await userEvent.type(field('name'), 'Riverside Grading');
    fireEvent.change(field('start_date'), { target: { value: '2026-05-10' } });
    fireEvent.change(field('estimated_end_date'), { target: { value: '2026-05-01' } });
    await userEvent.click(screen.getByRole('button', { name: 'Create Project' }));

    expect(onSubmit).not.toHaveBeenCalled();
    expect(screen.getByText('End date must be on or after start date')).toBeInTheDocument();
  });
});
