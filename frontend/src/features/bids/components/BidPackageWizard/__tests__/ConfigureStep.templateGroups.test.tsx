/**
 * Template grouping on the Configure step.
 *
 * Only the trade-matched "Recommended" templates show by default; General and
 * Other collapse behind one "Show N more templates" disclosure so the page
 * leads with the likely pick. Collapsing is purely visual — the same templates,
 * the same selection wiring.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { ConfigureStep } from '../ConfigureStep';
import type { Task } from '@/features/tasks/api/task.queries';
import type { WizardData } from '@/features/bids/types';
import type { BidTemplate } from '@/features/bid-templates/api/bid-template.queries';

// Controllable per test — some tests need "no recommended templates".
let templateItems: Partial<BidTemplate>[] = [];

vi.mock('@/features/bid-templates/hooks/useBidTemplates', () => ({
  useBidTemplates: () => ({ data: { items: templateItems }, isLoading: false }),
}));

vi.mock('@/features/bids/hooks/useProjectDocuments', () => ({
  useProjectDocuments: () => ({ data: [], isLoading: false }),
}));

vi.mock('@/features/projects/api/project-documents.mutations', () => ({
  uploadProjectDocument: vi.fn(),
}));

const REC = { id: 'rec1', name: 'Rec Template', trade_id: 'trade1', trade_name: 'Grading', is_lump_sum: false, item_count: 3 };
const GEN = { id: 'gen1', name: 'Gen Template', trade_id: null, trade_name: null, is_lump_sum: false, item_count: 2 };
const OTH = { id: 'oth1', name: 'Oth Template', trade_id: 'trade-other', trade_name: 'Blasting', is_lump_sum: false, item_count: 5 };

const task = { id: 't1', project_id: 'p1', trade_id: 'trade1', name: 'Mass Grading' } as unknown as Task;

function buildData(overrides: Partial<WizardData> = {}): WizardData {
  return {
    deadline: '2099-09-01T17:00',
    bidTemplateId: null,
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
  render(
    <ConfigureStep projectId="p1" task={task} data={data} onUpdate={onUpdate} onNext={vi.fn()} />,
  );
  return { onUpdate };
}

describe('ConfigureStep template groups', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    templateItems = [REC, GEN, OTH];
  });

  it('shows Recommended by default and hides General/Other behind the toggle', () => {
    renderStep();

    expect(screen.getByText('Rec Template')).toBeInTheDocument();
    expect(screen.queryByText('Gen Template')).not.toBeInTheDocument();
    expect(screen.queryByText('Oth Template')).not.toBeInTheDocument();

    // Count = general + other = 2.
    expect(screen.getByRole('button', { name: /show 2 more templates/i })).toBeInTheDocument();
  });

  it('reveals both sub-groups with their headings when expanded', () => {
    renderStep();

    fireEvent.click(screen.getByRole('button', { name: /show 2 more templates/i }));

    expect(screen.getByText('General Templates')).toBeInTheDocument();
    expect(screen.getByText('Other Templates')).toBeInTheDocument();
    expect(screen.getByText('Gen Template')).toBeInTheDocument();
    expect(screen.getByText('Oth Template')).toBeInTheDocument();
  });

  it('selecting a revealed template updates the wizard the same as any group', () => {
    const { onUpdate } = renderStep();

    fireEvent.click(screen.getByRole('button', { name: /show 2 more templates/i }));
    fireEvent.click(screen.getByText('Oth Template'));

    expect(onUpdate).toHaveBeenCalledWith({ bidTemplateId: 'oth1' });
  });

  it('opens the section on load when the current selection lives inside it', () => {
    renderStep(buildData({ bidTemplateId: 'oth1' }));

    // No click needed — the selected Other template is visible immediately.
    expect(screen.getByText('Oth Template')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /hide 2 more templates/i })).toBeInTheDocument();
  });

  it('still collapses by default when there are no recommended templates', () => {
    templateItems = [GEN, OTH];
    renderStep();

    // Rows hidden until expanded; and with nothing shown above, the label drops
    // the word "more".
    expect(screen.queryByText('Gen Template')).not.toBeInTheDocument();
    const toggle = screen.getByRole('button', { name: /show 2 templates/i });
    expect(toggle).toBeInTheDocument();

    fireEvent.click(toggle);
    expect(screen.getByText('Gen Template')).toBeInTheDocument();
  });

  it('shows no toggle when every template is recommended', () => {
    templateItems = [REC];
    renderStep();

    expect(screen.getByText('Rec Template')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /more template/i })).not.toBeInTheDocument();
  });
});
