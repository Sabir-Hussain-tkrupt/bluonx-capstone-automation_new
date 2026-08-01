import { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Archive, MoreHorizontal, Pencil, Trash2 } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { IconButton } from '@/components/ui/IconButton';
import { DropdownMenu, DropdownMenuItem } from '@/components/ui/DropdownMenu';
import { Card } from '@/components/ui/Card';
import { Tabs } from '@/components/ui/Tabs';
import { StatusBadge } from '@/components/ui/StatusBadge';
import { ConfirmDialog } from '@/components/ui/ConfirmDialog';
import { Skeleton } from '@/components/ui/Skeleton';
import { Alert } from '@/components/ui/Alert';
import { useToast } from '@/components/ui/Toast/useToast';
import { DocumentList } from '@/components/ui/DocumentList';
import { Field } from '@/components/ui/Field';
import { AddressNotLocatableBadge } from '@/components/shared/AddressNotLocatableBadge';
import { TaskList } from '@/features/tasks/components/TaskList';
import { useProject } from '@/features/projects/hooks/useProject';
import { useUpdateProject } from '@/features/projects/hooks/useUpdateProject';
import { useDeleteProject } from '@/features/projects/hooks/useDeleteProject';
import { useArchiveProject } from '@/features/projects/hooks/useArchiveProject';
import { useUnarchiveProject } from '@/features/projects/hooks/useUnarchiveProject';
import {
  useProjectDocumentsList,
  useDeleteProjectDocument,
  useProjectDocumentDownload,
} from '@/features/projects/hooks/useProjectDocuments';
import { ProjectForm } from '@/features/projects/components/ProjectForm';
import { ProjectDocumentUpload } from '@/features/projects/components/ProjectDocumentUpload';
import type { StatusVariant } from '@/components/ui/types';
import { formatCurrency, formatDateOnly } from '@/lib/format';
import { errorMessage, type ApiError } from '@/lib/api';
import { notifyGeocodeWarning } from '@/utils/geocodeToast';

const statusVariantMap: Record<string, StatusVariant> = {
  planning: 'info',
  active: 'success',
  on_hold: 'warning',
  completed: 'neutral',
  cancelled: 'danger',
};

type PendingAction =
  | { kind: 'deleteProject' }
  | { kind: 'archiveProject' }
  | { kind: 'deleteDocument'; docId: string; fileName: string }
  | null;

export function ProjectDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { toast } = useToast();

  const { data: project, isLoading, error, refetch, isFetching } = useProject(id!);
  const updateProjectMutation = useUpdateProject();
  const deleteProjectMutation = useDeleteProject();
  const archiveProjectMutation = useArchiveProject();
  const unarchiveProjectMutation = useUnarchiveProject();
  const {
    data: projectDocuments = [],
    isError: docsError,
    refetch: refetchDocs,
  } = useProjectDocumentsList(id!);
  const deleteDocMutation = useDeleteProjectDocument();
  const { download: downloadDoc, downloadingId } = useProjectDocumentDownload();

  const [activeTab, setActiveTab] = useState('overview');
  const [showEditForm, setShowEditForm] = useState(false);
  const [showUploadDoc, setShowUploadDoc] = useState(false);
  // One dialog for all three destructive actions, so their confirmations
  // cannot drift apart. Document delete used to fire with no confirmation.
  const [pending, setPending] = useState<PendingAction>(null);
  const closePending = () => setPending(null);

  if (isLoading) {
    return (
      <div className="space-y-6">
        <Skeleton height="32px" width="70%" />
        <Skeleton height="400px" />
      </div>
    );
  }

  if (error) {
    const status = (error as unknown as ApiError | undefined)?.status;
    if (status !== 404) {
      return (
        <Alert variant="danger" title="Could not load project">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <span>{errorMessage(error, 'Something went wrong. Please try again.')}</span>
            <Button variant="outline" size="sm" onClick={() => refetch()} isLoading={isFetching}>
              Retry
            </Button>
          </div>
        </Alert>
      );
    }
  }

  if (error || !project) {
    return (
      <Alert variant="danger" title="Project not found">
        The project you are looking for does not exist or has been deleted.
      </Alert>
    );
  }

  const handleUnarchive = () => {
    unarchiveProjectMutation.mutate(id!, {
      onSuccess: () => toast({ variant: 'success', message: 'Project unarchived.' }),
      onError: (err) => {
        toast({ variant: 'danger', message: errorMessage(err, 'Failed to unarchive project.') });
      },
    });
  };

  const handleConfirm = () => {
    if (!pending) return;
    if (pending.kind === 'deleteProject') {
      deleteProjectMutation.mutate(id!, {
        onSuccess: () => {
          closePending();
          toast({ variant: 'success', message: 'Project deleted.' });
          navigate('/projects');
        },
        onError: (err) => {
          closePending();
          toast({ variant: 'danger', message: errorMessage(err, 'Failed to delete project.') });
        },
      });
    } else if (pending.kind === 'archiveProject') {
      archiveProjectMutation.mutate(id!, {
        onSuccess: () => {
          closePending();
          toast({ variant: 'success', message: 'Project archived.' });
          navigate('/projects');
        },
        onError: (err) => {
          closePending();
          toast({ variant: 'danger', message: errorMessage(err, 'Failed to archive project.') });
        },
      });
    } else if (pending.kind === 'deleteDocument') {
      const { docId } = pending;
      deleteDocMutation.mutate(
        { projectId: id!, docId },
        {
          onSuccess: () => {
            closePending();
            toast({ variant: 'success', message: 'Document deleted.' });
          },
          onError: (err) => {
            closePending();
            toast({ variant: 'danger', message: errorMessage(err, 'Failed to delete document.') });
          },
        },
      );
    }
  };

  const confirmCopy = {
    deleteProject: {
      title: 'Delete Project',
      message: (
        <>
          Are you sure you want to delete <strong>{project.name}</strong>? This will
          soft-delete the project and it will no longer appear in lists.
        </>
      ),
      confirmText: 'Delete Project',
      confirmVariant: 'danger' as const,
      isLoading: deleteProjectMutation.isPending,
    },
    archiveProject: {
      title: 'Archive Project',
      message: (
        <>
          Archive <strong>{project.name}</strong>? This hides the project from your default
          view. You can find it later using the Archived filter. The project and all its data
          are preserved.
        </>
      ),
      confirmText: 'Archive Project',
      confirmVariant: 'primary' as const,
      isLoading: archiveProjectMutation.isPending,
    },
    deleteDocument: {
      title: 'Delete Document',
      message: (
        <>
          Delete <strong>{pending?.kind === 'deleteDocument' ? pending.fileName : ''}</strong>?
          This permanently removes the file.
        </>
      ),
      confirmText: 'Delete',
      confirmVariant: 'danger' as const,
      isLoading: deleteDocMutation.isPending,
    },
  };
  const activeCopy = pending ? confirmCopy[pending.kind] : null;

  const isArchived = !!project.archived_at;
  const canArchive = project.status !== 'active';

  const tabDefs = [
    { id: 'overview', label: 'Overview' },
    { id: 'tasks', label: 'Tasks' },
    { id: 'documents', label: 'Documents', count: projectDocuments.length },
  ];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0">
          <h1 className="truncate text-xl font-semibold text-secondary-900 sm:text-2xl">{project.name}</h1>
          <div className="mt-1 flex flex-wrap items-center gap-2">
            <StatusBadge status={project.status} variant={statusVariantMap[project.status] ?? 'neutral'} />
            {isArchived && <StatusBadge status="archived" variant="neutral" />}
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          {!isArchived && (
            <>
              <Button
                variant="primary"
                leftIcon={<Pencil className="h-4 w-4" />}
                onClick={() => setShowEditForm(true)}
              >
                Edit
              </Button>
              <span
                title={!canArchive ? 'Active projects cannot be archived' : undefined}
                className="inline-flex"
              >
                <Button
                  variant="outline"
                  leftIcon={<Archive className="h-4 w-4" />}
                  disabled={!canArchive}
                  onClick={() => setPending({ kind: 'archiveProject' })}
                >
                  Archive
                </Button>
              </span>
            </>
          )}
          {isArchived && (
            <Button
              variant="primary"
              onClick={handleUnarchive}
              isLoading={unarchiveProjectMutation.isPending}
            >
              Unarchive
            </Button>
          )}
          <DropdownMenu
            trigger={
              <IconButton
                variant="outline"
                size="md"
                icon={<MoreHorizontal className="h-4 w-4" />}
                aria-label="More actions"
              />
            }
          >
            <DropdownMenuItem
              icon={<Trash2 className="h-4 w-4" />}
              destructive
              onClick={() => setPending({ kind: 'deleteProject' })}
            >
              Delete
            </DropdownMenuItem>
          </DropdownMenu>
        </div>
      </div>

      {isArchived && (
        <Alert variant="info" title="This project is archived">
          Unarchive it to make changes.
        </Alert>
      )}

      {/* Tabs */}
      <Tabs tabs={tabDefs} activeTab={activeTab} onChange={setActiveTab}>
        {activeTab === 'overview' && (
          <Card>
            <div className="grid grid-cols-1 gap-6 p-6 md:grid-cols-2">
              <div>
                <h3 className="mb-4 border-b border-secondary-100 pb-2 text-base font-semibold text-secondary-900">Location</h3>
                <dl className="divide-y divide-secondary-100">
                  <Field
                    label="Address"
                    value={
                      <span className="inline-flex flex-wrap items-center justify-end gap-2">
                        {project.address}
                        <AddressNotLocatableBadge
                          address={project.address}
                          latitude={project.latitude}
                          entity="project"
                        />
                      </span>
                    }
                  />
                  <Field label="City" value={project.city} />
                  <Field label="State" value={project.state} />
                  <Field label="ZIP Code" value={project.zip_code} />
                </dl>
              </div>
              <div>
                <h3 className="mb-4 border-b border-secondary-100 pb-2 text-base font-semibold text-secondary-900">Budget & Schedule</h3>
                <dl className="divide-y divide-secondary-100">
                  <Field label="Budget" value={formatCurrency(project.budget)} />
                  <Field label="Start Date" value={formatDateOnly(project.start_date)} />
                  <Field label="Est. End Date" value={formatDateOnly(project.estimated_end_date)} />
                </dl>
              </div>
              {project.description && (
                <div className="md:col-span-2">
                  <h3 className="mb-4 border-b border-secondary-100 pb-2 text-base font-semibold text-secondary-900">Description</h3>
                  <p className="text-sm text-secondary-700 whitespace-pre-wrap">{project.description}</p>
                </div>
              )}
            </div>
          </Card>
        )}

        {activeTab === 'tasks' && (
          <TaskList projectId={id!} projectBudget={project.budget} readOnly={isArchived} />
        )}

        {activeTab === 'documents' && (
          <div className="space-y-4">
            {!isArchived && (
              <div className="flex justify-end">
                <Button size="sm" onClick={() => setShowUploadDoc(true)}>+ Upload Document</Button>
              </div>
            )}
            {docsError && (
              <Alert variant="danger" title="Could not load documents">
                <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                  <span>The document list could not be loaded.</span>
                  <Button variant="outline" size="sm" onClick={() => refetchDocs()}>Retry</Button>
                </div>
              </Alert>
            )}
            <DocumentList
              documents={projectDocuments}
              onDownload={(docId) => downloadDoc(id!, docId)}
              onDelete={isArchived ? undefined : (docId) => {
                const doc = projectDocuments.find((d) => d.id === docId);
                setPending({ kind: 'deleteDocument', docId, fileName: doc?.file_name ?? 'this document' });
              }}
              isDeleting={deleteDocMutation.isPending ? deleteDocMutation.variables?.docId ?? null : null}
              isDownloading={downloadingId}
              emptyMessage="No documents uploaded yet. Upload civil plans, drawings, specs, or site photos."
            />
            <ProjectDocumentUpload
              projectId={id!}
              isOpen={showUploadDoc}
              onClose={() => setShowUploadDoc(false)}
            />
          </div>
        )}
      </Tabs>

      {/* Edit Project Modal.
          Mounted only while open, so React Hook Form's mount-time defaultValues
          cannot keep serving pre-edit values after a save. */}
      {showEditForm && (
        <ProjectForm
          isOpen={showEditForm}
          onClose={() => setShowEditForm(false)}
          project={project}
          isLoading={updateProjectMutation.isPending}
          onSubmit={(formData) => {
            updateProjectMutation.mutate(
              { id: id!, ...formData } as Parameters<typeof updateProjectMutation.mutate>[0],
              {
                onSuccess: (updated) => {
                  setShowEditForm(false);
                  toast({ variant: 'success', message: 'Project updated.' });
                  notifyGeocodeWarning(toast, updated);
                },
                onError: (err) => toast({ variant: 'danger', message: errorMessage(err, 'Failed to update project.') }),
              },
            );
          }}
        />
      )}

      {/* One dialog for delete project, archive project, and delete document. */}
      <ConfirmDialog
        isOpen={pending !== null}
        title={activeCopy?.title ?? ''}
        message={activeCopy?.message ?? ''}
        confirmText={activeCopy?.confirmText}
        confirmVariant={activeCopy?.confirmVariant}
        isLoading={activeCopy?.isLoading ?? false}
        onConfirm={handleConfirm}
        onCancel={closePending}
      />
    </div>
  );
}
