import { useEffect, useMemo, useState } from 'react';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { FormField } from '@/components/ui/FormField';
import { TextInput } from '@/components/ui/TextInput';
import { Checkbox } from '@/components/ui/Checkbox';
import { Skeleton } from '@/components/ui/Skeleton';
import { Alert } from '@/components/ui/Alert';
import { StatusBadge } from '@/components/ui/StatusBadge';
import { useBidTemplates } from '@/features/bid-templates/hooks/useBidTemplates';
import { useProjectDocuments } from '@/features/bids/hooks/useProjectDocuments';
import type { Task } from '@/features/tasks/api/task.queries';
import type { WizardData } from '@/features/bids/types';
import type { BidTemplate } from '@/features/bid-templates/api/bid-template.queries';
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

  const [errors, setErrors] = useState<{ deadline?: string; template?: string }>({});

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

  const handleDocToggle = (docId: string) => {
    const next = selectedIds.includes(docId)
      ? selectedIds.filter((id) => id !== docId)
      : [...selectedIds, docId];
    onUpdate({ documentIds: next });
  };

  const handleNext = () => {
    const newErrors: { deadline?: string; template?: string } = {};

    if (!data.deadline) {
      newErrors.deadline = 'Deadline is required.';
    } else if (new Date(data.deadline) <= new Date()) {
      newErrors.deadline = 'Deadline must be in the future.';
    }

    if (!data.bidTemplateId) {
      newErrors.template = 'Please select a bid template.';
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
                  onSelect={(id) => {
                    onUpdate({ bidTemplateId: id });
                    if (errors.template) setErrors((prev) => ({ ...prev, template: undefined }));
                  }}
                  showStar
                />
              )}
              {general.length > 0 && (
                <TemplateGroup
                  title="General Templates"
                  templates={general}
                  selectedId={data.bidTemplateId}
                  onSelect={(id) => {
                    onUpdate({ bidTemplateId: id });
                    if (errors.template) setErrors((prev) => ({ ...prev, template: undefined }));
                  }}
                />
              )}
              {other.length > 0 && (
                <TemplateGroup
                  title="Other Templates"
                  templates={other}
                  selectedId={data.bidTemplateId}
                  onSelect={(id) => {
                    onUpdate({ bidTemplateId: id });
                    if (errors.template) setErrors((prev) => ({ ...prev, template: undefined }));
                  }}
                />
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
