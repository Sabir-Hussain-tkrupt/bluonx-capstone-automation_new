import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { ProjectContextPanel } from '../ProjectContextPanel';
import type { PortalProject, PortalTask } from '../../types/portal';
import { makePortalBidPackage as pkg } from '../../test/fixtures';

const project: PortalProject = {
  id: 'p1',
  name: 'Phoenix Park',
  location: 'AZ',
  address: '1 Main St',
};

const task: PortalTask = {
  id: 't1',
  name: 'Mass Grading',
  description: 'Bring pads to subgrade.',
  trade_name: 'Earthwork',
};

describe('ProjectContextPanel — desired_start_date', () => {
  it('renders the desired-start row when the package has one', () => {
    render(
      <ProjectContextPanel
        project={project}
        task={task}
        bidPackage={pkg({ desired_start_date: '2026-09-15' })}
      />,
    );
    // Either label spelling is acceptable.
    expect(screen.getByText(/Desired start/i)).toBeInTheDocument();
    // The formatted date or the raw ISO is acceptable — anything that
    // proves the value reached the DOM. Look for the YYYY-MM-DD digits.
    expect(screen.getByText(/2026/)).toBeInTheDocument();
  });

  it('omits the desired-start row when the package has none', () => {
    render(
      <ProjectContextPanel
        project={project}
        task={task}
        bidPackage={pkg({ desired_start_date: null })}
      />,
    );
    expect(screen.queryByText(/Desired start/i)).not.toBeInTheDocument();
  });
});
