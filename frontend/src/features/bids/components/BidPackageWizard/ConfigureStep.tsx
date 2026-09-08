import { useEffect, useMemo, useState } from 'react';
import { ChevronDown } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { FormField } from '@/components/ui/FormField';
import { TextInput } from '@/components/ui/TextInput';
import { Checkbox } from '@/components/ui/Checkbox';
import { Skeleton } from '@/components/ui/Skeleton';
import { Alert } from '@/components/ui/Alert';
import { StatusBadge } from '@/components/ui/StatusBadge';
import { FileUpload } from '@/components/ui/FileUpload';
import { useBidTemplates } from '@/features/bid-templates/hooks/useBidTemplates';
import { useProjectDocuments } from '@/features/bids/hooks/useProjectDocuments';
import { uploadProjectDocument } from '@/features/projects/api/project-documents.mutations';
import type { Task } from '@/features/tasks/api/task.queries';
import type { WizardData } from '@/features/bids/types';
import type { BidTemplate } from '@/features/bid-templates/api/bid-template.queries';
import {
  PROJECT_DOCUMENT_ACCEPT,
  PROJECT_DOCUMENT_HINT,
  PROJECT_DOCUMENT_MAX_MB,
} from '@/constants/uploads';
import { cn } from '@/utils/cn';

interface ConfigureStepProps {
  projectId: string;
  task: Task;
  data: WizardData;
  onUpdate: (partial: Partial<WizardData>) => void;
  onNext: () => void;
}

function formatFileSize(bytes: number | null): string {
  if (!bytes) return '';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function ConfigureStep({ projectId, task, data, onUpdate, onNext }: ConfigureStepProps) {
  const { data: templatesData, isLoading: templatesLoading } = useBidTemplates({ page_size: 100 });
  const { data: documents = [], isLoading: docsLoading } = useProjectDocuments(projectId);

  const [errors, setErrors] = useState<{ deadline?: string; template?: string; sow?: string }>(
    {},
  );
  const [sowUploading, setSowUploading] = useState(false);
  // Replacing an existing SoW is behind a toggle so the uploaded state stays a
  // compact summary line rather than a permanent dropzone.
  const [replacingSow, setReplacingSow] = useState(false);

  const setSowError = (message: string | undefined) =>
    setErrors((prev) => ({ ...prev, sow: message }));

  const handleSowSelect = async (file: File | undefined) => {
    if (!file) return;
    setSowUploading(true);
    setSowError(undefined);
    try {
      const formData = new FormData();
      formData.append('file', file);
      formData.append('document_kind', 'scope_of_work');
      const doc = (await uploadProjectDocument(projectId, formData)) as {
        id: string;
        file_name: string;
      };
      onUpdate({ scopeOfWorkDocumentId: doc.id, scopeOfWorkFileName: doc.file_name });
      setReplacingSow(false);
    } catch {
      setErrors((prev) => ({ ...prev, sow: 'Failed to upload the Scope of Work. Try again.' }));
    } finally {
      setSowUploading(false);
    }
  };

  /**
   * One dropzone definition for both the initial upload and the replace, so the
   * two cannot drift apart again. They previously carried different accept
   * lists (5 extensions vs 15) against the same bucket, which made a first
   * .dwg scope of work unselectable while replacing one with that same file
   * worked. Neither had a size cap.
   */
  const sowUpload = (label: string) => (
    <FileUpload
      accept={PROJECT_DOCUMENT_ACCEPT}
      maxSizeMB={PROJECT_DOCUMENT_MAX_MB}
      label={label}
      hint={PROJECT_DOCUMENT_HINT}
      uploading={sowUploading}
      onFilesSelected={(files) => handleSowSelect(files[0])}
      onError={setSowError}
      // The summary box above already names the uploaded file; the component's
      // own list would show it a second time.
      showFileList={false}
    />
  );

  // Seed document IDs on first load (all pre-checked). Guard on `null`
  // (not-yet-seeded), NOT on length: an empty array means the user
  // deliberately deselected everything and must be left untouched.
  useEffect(() => {
    if (data.documentIds === null && documents.length > 0) {
      onUpdate({ documentIds: documents.map((d) => d.id) });
    }
  }, [documents, data.documentIds, onUpdate]);

  // Safe view for reads while documentIds is still null (pre-seed render).
  const selectedIds = data.documentIds ?? [];

  const templates = templatesData?.items ?? [];

  // Group templates: Recommended (trade match), General (null trade), Other
  const { recommended, general, other } = useMemo(() => {
    const rec: BidTemplate[] = [];
    const gen: BidTemplate[] = [];
    const oth: BidTemplate[] = [];

    for (const t of templates) {
      if (t.trade_id === task.trade_id) {
        rec.push(t);
      } else if (!t.trade_id) {
        gen.push(t);
      } else {
        oth.push(t);
      }
    }

    return { recommended: rec, general: gen, other: oth };
  }, [templates, task.trade_id]);

  const moreCount = general.length + other.length;

  // The non-recommended templates start collapsed to keep this page short. The
  // one case that must NOT start collapsed is when the current selection is a
  // General/Other template (editing/revisiting a package) — hiding it would look
  // like nothing is chosen. Seeded once from mount-time props; the selection
  // only changes afterward via a click inside the already-open region.
  const [showMoreTemplates, setShowMoreTemplates] = useState(
    () =>
      general.some((t) => t.id === data.bidTemplateId) ||
      other.some((t) => t.id === data.bidTemplateId),
  );

  // One selection handler for every group so the three renders can't drift.
  const handleSelectTemplate = (id: string) => {
    onUpdate({ bidTemplateId: id });
    if (errors.template) setErrors((prev) => ({ ...prev, template: undefined }));
  };

  const handleDocToggle = (docId: string) => {
    const next = selectedIds.includes(docId)
      ? selectedIds.filter((id) => id !== docId)
      : [...selectedIds, docId];
    onUpdate({ documentIds: next });
  };

  const handleNext = () => {
    const newErrors: { deadline?: string; template?: string; sow?: string } = {};

    if (!data.deadline) {
      newErrors.deadline = 'Deadline is required.';
    } else if (new Date(data.deadline) <= new Date()) {
      newErrors.deadline = 'Deadline must be in the future.';
    }

    if (!data.bidTemplateId) {
      newErrors.template = 'Please select a bid template.';
    }

    if (!data.scopeOfWorkDocumentId) {
      newErrors.sow = 'A Scope of Work document is required.';
    }

    if (Object.keys(newErrors).length > 0) {
      setErrors(newErrors);
      return;
    }

    setErrors({});
    onNext();
  };

  return (
    <div className="space-y-6">
      {/* Deadline */}
      <Card>
        <div className="p-6">
          <h3 className="mb-4 text-sm font-semibold text-secondary-900">Bid Deadline</h3>
          <FormField
            label="Deadline"
            required
            error={errors.deadline}
            hint="Vendors must submit their bids before this date and time."
          >
            <TextInput
              type="datetime-local"
              value={data.deadline}
              onChange={(e) => {
                onUpdate({ deadline: e.target.value });
                if (errors.deadline) setErrors((prev) => ({ ...prev, deadline: undefined }));
              }}
              error={!!errors.deadline}
            />
          </FormField>
        </div>
      </Card>

      {/* Desired Start Date (Task 8.1.5) */}
      <Card>
        <div className="p-6">
          <h3 className="mb-4 text-sm font-semibold text-secondary-900">
            Desired Start Date
          </h3>
          <FormField
            label="Desired start date"
            htmlFor="desired-start-date"
            hint="Optional — target start date you'd like vendors to bid against. Leave blank to keep timing flexible."
          >
            <TextInput
              id="desired-start-date"
              type="date"
              value={data.desiredStartDate ?? ''}
              onChange={(e) => {
                const v = e.target.value;
                onUpdate({ desiredStartDate: v === '' ? null : v });
              }}
            />
          </FormField>
        </div>
      </Card>

      {/* Scope of Work (required) */}
      <Card>
        <div className="p-6">
          <h3 className="mb-1 text-sm font-semibold text-secondary-900">
            Scope of Work
            <span className="ml-1 text-danger-500">*</span>
          </h3>
          <p className="mb-4 text-xs text-secondary-500">
            Upload the Scope of Work for this bid package. Vendors must review and attest to
            it before submitting a bid. Required.
          </p>

          {errors.sow && (
            <Alert variant="danger" className="mb-4">
              {errors.sow}
            </Alert>
          )}

          {data.scopeOfWorkDocumentId ? (
            <div className="space-y-3">
              <div className="flex items-center justify-between rounded-lg border border-success-200 bg-success-50 px-4 py-3">
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium text-secondary-900">
                    {data.scopeOfWorkFileName ?? 'Scope of Work uploaded'}
                  </p>
                  <p className="text-xs text-success-700">Uploaded</p>
                </div>
                <button
                  type="button"
                  onClick={() => {
                    setReplacingSow((v) => !v);
                    setSowError(undefined);
                  }}
                  disabled={sowUploading}
                  aria-expanded={replacingSow}
                  className="shrink-0 text-xs font-medium text-primary-600 hover:text-primary-700 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {replacingSow ? 'Cancel' : 'Replace'}
                </button>
              </div>
              {replacingSow && sowUpload('Drop a replacement here or click to browse')}
            </div>
          ) : (
            sowUpload('Click to upload a Scope of Work document')
          )}
        </div>
      </Card>

      {/* Template Selection */}
      <Card>
        <div className="p-6">
          <h3 className="mb-1 text-sm font-semibold text-secondary-900">Bid Template</h3>
          <p className="mb-4 text-xs text-secondary-500">
            Select a template that vendors will use to structure their bids.
          </p>

          {errors.template && (
            <Alert variant="danger" className="mb-4">
              {errors.template}
            </Alert>
          )}

          {templatesLoading ? (
            <div className="space-y-3">
              <Skeleton height="60px" />
              <Skeleton height="60px" />
              <Skeleton height="60px" />
            </div>
          ) : templates.length === 0 ? (
            <Alert variant="warning" title="No templates available">
              Create a bid template first before creating a bid package.
            </Alert>
          ) : (
            <div className="space-y-5">
              {recommended.length > 0 && (
                <TemplateGroup
                  title="Recommended"
                  subtitle="Matches this task's trade"
                  templates={recommended}
                  selectedId={data.bidTemplateId}
                  onSelect={handleSelectTemplate}
                  showStar
                />
              )}

              {/* General + Other collapsed behind one disclosure so the page
                  leads with the trade-matched picks. Mirrors the "Show N
                  disqualified vendors" toggle on the Select Vendors step. */}
              {moreCount > 0 && (
                <div>
                  <button
                    type="button"
                    onClick={() => setShowMoreTemplates((v) => !v)}
                    aria-expanded={showMoreTemplates}
                    className="group flex w-full items-center justify-between rounded-lg border border-secondary-200 px-3 py-2 text-left transition-colors hover:border-secondary-300 hover:bg-secondary-50"
                  >
                    <span className="text-xs font-semibold uppercase tracking-wide text-secondary-500 transition-colors group-hover:text-secondary-700">
                      {showMoreTemplates ? 'Hide' : 'Show'} {moreCount}{' '}
                      {recommended.length > 0 ? 'more ' : ''}template
                      {moreCount !== 1 ? 's' : ''}
                    </span>
                    <ChevronDown
                      className={cn(
                        'h-4 w-4 text-secondary-400 transition-transform group-hover:text-secondary-600',
                        showMoreTemplates && 'rotate-180',
                      )}
                      aria-hidden="true"
                    />
                  </button>

                  {showMoreTemplates && (
                    <div className="mt-3 space-y-5">
                      {general.length > 0 && (
                        <TemplateGroup
                          title="General Templates"
                          templates={general}
                          selectedId={data.bidTemplateId}
                          onSelect={handleSelectTemplate}
                        />
                      )}
                      {other.length > 0 && (
                        <TemplateGroup
                          title="Other Templates"
                          templates={other}
                          selectedId={data.bidTemplateId}
                          onSelect={handleSelectTemplate}
                        />
                      )}
                    </div>
                  )}
                </div>
              )}
            </div>
          )}
        </div>
      </Card>

      {/* Instructions to Vendors */}
      <Card>
        <div className="p-6">
          <h3 className="mb-1 text-sm font-semibold text-secondary-900">
            Instructions to Vendors
            <span className="ml-1 text-xs font-normal text-secondary-400">(optional)</span>
          </h3>
          <p className="mb-4 text-xs text-secondary-500">
            Bid-submission guidance shown to vendors in the portal and invitation email.
            Examples: &ldquo;unit prices all-inclusive&rdquo;, &ldquo;bid held firm for 30 days&rdquo;.
          </p>
          <textarea
            value={data.instructions}
            onChange={(e) => onUpdate({ instructions: e.target.value })}
            rows={3}
            maxLength={2000}
            placeholder="Enter any bid-submission instructions for vendors..."
            className="w-full rounded-lg border border-secondary-300 px-3 py-2 text-sm text-secondary-900 placeholder:text-secondary-400 focus:border-primary-500 focus:outline-none focus:ring-1 focus:ring-primary-500"
          />
          <p className="mt-1 text-right text-xs text-secondary-400">
            {data.instructions.length} / 2,000
          </p>
        </div>
      </Card>

      {/* Project Documents */}
      <Card>
        <div className="p-6">
          <div className="mb-4 flex items-center justify-between">
            <div>
              <h3 className="text-sm font-semibold text-secondary-900">Project Documents</h3>
              <p className="mt-0.5 text-xs text-secondary-500">
                Select documents to include with the bid package.
              </p>
            </div>
            {documents.length > 0 && (
              <button
                type="button"
                onClick={() => {
                  const allSelected = selectedIds.length === documents.length;
                  onUpdate({ documentIds: allSelected ? [] : documents.map((d) => d.id) });
                }}
                className="text-xs font-medium text-primary-600 hover:text-primary-700"
              >
                {selectedIds.length === documents.length ? 'Deselect All' : 'Select All'}
              </button>
            )}
          </div>

          {docsLoading ? (
            <div className="space-y-2">
              <Skeleton height="44px" />
              <Skeleton height="44px" />
            </div>
          ) : documents.length === 0 ? (
            <p className="text-sm text-secondary-500">No project documents uploaded yet.</p>
          ) : (
            <div className="divide-y divide-secondary-100">
              {documents.map((doc) => (
                <Checkbox
                  key={doc.id}
                  label={doc.file_name}
                  description={[doc.file_type, formatFileSize(doc.file_size)]
                    .filter(Boolean)
                    .join(' · ')}
                  checked={selectedIds.includes(doc.id)}
                  onChange={() => handleDocToggle(doc.id)}
                />
              ))}
            </div>
          )}
        </div>
      </Card>

      {/* Footer */}
      <div className="flex justify-end">
        <Button onClick={handleNext}>Next: Select Vendors</Button>
      </div>
    </div>
  );
}

// ─── Template Group Sub-component ────────────────────────────────────

interface TemplateGroupProps {
  title: string;
  subtitle?: string;
  templates: BidTemplate[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  showStar?: boolean;
}

function TemplateGroup({
  title,
  subtitle,
  templates,
  selectedId,
  onSelect,
  showStar,
}: TemplateGroupProps) {
  return (
    <div>
      <div className="mb-2">
        <h4 className="text-xs font-semibold uppercase tracking-wide text-secondary-500">
          {showStar && <span className="mr-1 text-warning-500">&#9733;</span>}
          {title}
        </h4>
        {subtitle && <p className="text-xs text-secondary-400">{subtitle}</p>}
      </div>
      <div className="space-y-2">
        {templates.map((t) => (
          <button
            key={t.id}
            type="button"
            onClick={() => onSelect(t.id)}
            className={cn(
              'flex w-full items-center justify-between rounded-lg border-2 px-4 py-3 text-left transition-colors',
              selectedId === t.id
                ? 'border-primary-500 bg-primary-50'
                : 'border-secondary-200 hover:border-secondary-300 hover:bg-secondary-50',
            )}
          >
            <div className="min-w-0">
              <span className="text-sm font-medium text-secondary-900">{t.name}</span>
              {t.trade_name && (
                <span className="ml-2 text-xs text-secondary-400">{t.trade_name}</span>
              )}
            </div>
            <div className="flex shrink-0 items-center gap-2">
              <StatusBadge
                status={t.is_lump_sum ? 'Lump Sum' : 'Structured'}
                variant={t.is_lump_sum ? 'info' : 'neutral'}
                size="sm"
                dot={false}
              />
              <span className="text-xs text-secondary-400">{t.item_count} items</span>
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}
