import { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { Tabs } from '@/components/ui/Tabs';
import { StatusBadge } from '@/components/ui/StatusBadge';
import { Modal } from '@/components/ui/Modal';
import { Skeleton } from '@/components/ui/Skeleton';
import { Alert } from '@/components/ui/Alert';
import { EmptyState } from '@/components/ui/EmptyState';
import { useToast } from '@/components/ui/Toast/useToast';
import { TaskList } from '@/features/tasks/components/TaskList';
import { useProject } from '@/features/projects/hooks/useProject';
import { useUpdateProject } from '@/features/projects/hooks/useUpdateProject';
import { useDeleteProject } from '@/features/projects/hooks/useDeleteProject';
import { ProjectForm } from '@/features/projects/components/ProjectForm';
import type { StatusVariant } from '@/components/ui/types';

const statusVariantMap: Record<string, StatusVariant> = {
  planning: 'info',
  active: 'success',
  on_hold: 'warning',
  completed: 'neutral',
  cancelled: 'danger',
};

function InfoRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex justify-between gap-4 py-2 text-sm">
      <dt className="shrink-0 text-secondary-500">{label}</dt>
      <dd className="text-right text-secondary-900">{value || '\u2014'}</dd>
    </div>
  );
}

function formatCurrency(value: number | null): string {
  if (value == null) return '\u2014';
  return Number(value).toLocaleString('en-US', { style: 'currency', currency: 'USD', minimumFractionDigits: 0, maximumFractionDigits: 0 });
}

function formatDate(value: string | null): string {
  if (!value) return '\u2014';
  return new Date(value + 'T00:00:00').toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
}

export function ProjectDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { toast } = useToast();

  const { data: project, isLoading, error } = useProject(id!);
  const updateProjectMutation = useUpdateProject();
  const deleteProjectMutation = useDeleteProject();

  const [activeTab, setActiveTab] = useState('overview');
  const [showEditForm, setShowEditForm] = useState(false);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);

  if (isLoading) {
    return (
      <div className="space-y-6">
        <Skeleton height="32px" width="70%" />
        <Skeleton height="400px" />
      </div>
    );
  }

  if (error || !project) {
    return (
      <Alert variant="danger" title="Project not found">
        The project you are looking for does not exist or has been deleted.
      </Alert>
    );
  }

  const handleDelete = () => {
    deleteProjectMutation.mutate(id!, {
      onSuccess: () => {
        toast({ variant: 'success', message: 'Project deleted.' });
        navigate('/projects');
      },
      onError: () => toast({ variant: 'danger', message: 'Failed to delete project.' }),
    });
  };

  const tabDefs = [
    { id: 'overview', label: 'Overview' },
    { id: 'tasks', label: 'Tasks' },
    { id: 'documents', label: 'Documents' },
  ];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex min-w-0 items-center gap-3">
          <button
            type="button"
            onClick={() => navigate('/projects')}
            className="shrink-0 rounded-lg p-1 text-secondary-400 hover:bg-secondary-100 hover:text-secondary-600"
          >
            <svg className="h-5 w-5" viewBox="0 0 20 20" fill="currentColor">
              <path
                fillRule="evenodd"
                d="M17 10a.75.75 0 01-.75.75H5.612l4.158 3.96a.75.75 0 11-1.04 1.08l-5.5-5.25a.75.75 0 010-1.08l5.5-5.25a.75.75 0 111.04 1.08L5.612 9.25H16.25A.75.75 0 0117 10z"
                clipRule="evenodd"
              />
            </svg>
          </button>
          <div className="min-w-0">
            <h1 className="truncate text-xl font-semibold text-secondary-900 sm:text-2xl">{project.name}</h1>
            <div className="mt-1 flex flex-wrap items-center gap-2">
              <StatusBadge status={project.status} variant={statusVariantMap[project.status] ?? 'neutral'} />
            </div>
          </div>
        </div>
        <div className="flex shrink-0 gap-2">
          <Button variant="outline" onClick={() => setShowEditForm(true)}>Edit</Button>
          <Button variant="danger" onClick={() => setShowDeleteConfirm(true)}>Delete</Button>
        </div>
      </div>

      {/* Tabs */}
      <Tabs tabs={tabDefs} activeTab={activeTab} onChange={setActiveTab}>
        {activeTab === 'overview' && (
          <Card>
            <div className="grid grid-cols-1 gap-6 p-6 md:grid-cols-2">
              <div>
                <h3 className="mb-3 text-sm font-semibold text-secondary-900">Location</h3>
                <dl className="divide-y divide-secondary-100">
                  <InfoRow label="Address" value={project.address} />
                  <InfoRow label="City" value={project.city} />
                  <InfoRow label="State" value={project.state} />
                  <InfoRow label="ZIP Code" value={project.zip_code} />
                </dl>
              </div>
              <div>
                <h3 className="mb-3 text-sm font-semibold text-secondary-900">Budget & Schedule</h3>
                <dl className="divide-y divide-secondary-100">
                  <InfoRow label="Budget" value={formatCurrency(project.budget)} />
                  <InfoRow label="Start Date" value={formatDate(project.start_date)} />
                  <InfoRow label="Est. End Date" value={formatDate(project.estimated_end_date)} />
                </dl>
              </div>
              {project.description && (
                <div className="md:col-span-2">
                  <h3 className="mb-2 text-sm font-semibold text-secondary-900">Description</h3>
                  <p className="text-sm text-secondary-700 whitespace-pre-wrap">{project.description}</p>
                </div>
              )}
            </div>
          </Card>
        )}

        {activeTab === 'tasks' && (
          <TaskList projectId={id!} projectBudget={project.budget} />
        )}

        {activeTab === 'documents' && (
          <EmptyState
            title="Documents"
            description="Document management will be available in a future update (Task 3.4)."
          />
        )}
      </Tabs>

      {/* Edit Project Modal */}
      <ProjectForm
        isOpen={showEditForm}
        onClose={() => setShowEditForm(false)}
        project={project}
        isLoading={updateProjectMutation.isPending}
        onSubmit={(formData) => {
          updateProjectMutation.mutate(
            { id: id!, ...formData } as Parameters<typeof updateProjectMutation.mutate>[0],
            {
              onSuccess: () => { setShowEditForm(false); toast({ variant: 'success', message: 'Project updated.' }); },
              onError: () => toast({ variant: 'danger', message: 'Failed to update project.' }),
            },
          );
        }}
      />

      {/* Delete Confirmation */}
      <Modal
        isOpen={showDeleteConfirm}
        onClose={() => setShowDeleteConfirm(false)}
        title="Delete Project"
        size="sm"
        footer={
          <>
            <Button variant="ghost" onClick={() => setShowDeleteConfirm(false)}>Cancel</Button>
            <Button variant="danger" onClick={handleDelete} isLoading={deleteProjectMutation.isPending}>Delete Project</Button>
          </>
        }
      >
        <p className="text-sm text-secondary-600">
          Are you sure you want to delete <strong>{project.name}</strong>?
          This action will soft-delete the project and it will no longer appear in lists.
        </p>
      </Modal>
    </div>
  );
}
