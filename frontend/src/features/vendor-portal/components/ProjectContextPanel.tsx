import { Card } from '@/components/ui';
import type { PortalBidPackage, PortalProject, PortalTask } from '../types/portal';

export interface ProjectContextPanelProps {
  project: PortalProject;
  task: PortalTask;
  bidPackage: PortalBidPackage;
}

export function ProjectContextPanel({
  project,
  task,
  bidPackage,
}: ProjectContextPanelProps) {
  return (
    <Card title="Project & Task" subtitle="Bid package details for this invitation" padding="md">
      <dl className="grid gap-4 sm:grid-cols-2">
        <div>
          <dt className="text-xs font-medium tracking-wide text-secondary-500 uppercase">
            Project
          </dt>
          <dd className="mt-1 text-sm font-semibold text-secondary-900">{project.name}</dd>
          <p className="text-xs text-secondary-500">{project.address}</p>
        </div>
        {/* <div>
          <dt className="text-xs font-medium tracking-wide text-secondary-500 uppercase">
            Trade
          </dt>
          <dd className="mt-1 text-sm font-semibold text-secondary-900">{task.trade_name}</dd>
          <p className="text-xs text-secondary-500">Round {bidPackage.round_number}</p>
        </div> */}
        <div className="sm:col-span-2">
          <dt className="text-xs font-medium tracking-wide text-secondary-500 uppercase">
            Task
          </dt>
          <dd className="mt-1 text-sm font-semibold text-secondary-900">{task.name}</dd>
          <p className="mt-1 text-sm text-secondary-600">{task.description}</p>
        </div>
        {bidPackage.desired_start_date && (
          <div>
            <dt className="text-xs font-medium tracking-wide text-secondary-500 uppercase">
              Desired start
            </dt>
            <dd className="mt-1 text-sm font-semibold text-secondary-900">
              {bidPackage.desired_start_date}
            </dd>
            <p className="text-xs text-secondary-500">
              Target start the PM would like vendors to bid against.
            </p>
          </div>
        )}
        {bidPackage.instructions && (
          <div className="sm:col-span-2">
            <dt className="text-xs font-medium tracking-wide text-secondary-500 uppercase">
              Instructions
            </dt>
            <dd className="mt-1 rounded-md bg-secondary-50 p-3 text-sm text-secondary-700">
              {bidPackage.instructions}
            </dd>
          </div>
        )}
      </dl>
    </Card>
  );
}
