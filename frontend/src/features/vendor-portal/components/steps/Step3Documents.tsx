import { useState } from 'react';
import { Alert, Button, Card, FileUpload, FormField, useToast } from '@/components/ui';
import {
  deleteAttachment,
  uploadAttachment,
} from '../../services/portalApi';
import type { BidFormState, FormAttachment } from '../../types/portal';
import { PortalApiError } from '../../types/portal';

const ACCEPT_TYPES = 'application/pdf,image/jpeg,image/png';
const MAX_FILE_SIZE_MB = 10;
const MAX_NOTES_LENGTH = 2000;

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export interface Step3DocumentsProps {
  state: BidFormState;
  onUpdateNotes: (value: string) => void;
  onAddAttachment: (attachment: FormAttachment) => void;
  onRemoveAttachment: (id: string) => void;
  onNext: () => void;
  onBack: () => void;
  onSaveDraft: () => void;
  /**
   * Returns a submission id, creating a draft if one doesn't exist yet.
   * Uploads always belong to a real submission row on the backend.
   */
  ensureSubmissionId: () => Promise<string>;
  /** Called if a write hits 423 DEADLINE_PASSED so BidFormPage can surface the modal. */
  onDeadlinePassed: () => void;
  /** When the deadline has already passed, uploads/removals are locked out. */
  disabled?: boolean;
}

export function Step3Documents({
  state,
  onUpdateNotes,
  onAddAttachment,
  onRemoveAttachment,
  onNext,
  onBack,
  onSaveDraft,
  ensureSubmissionId,
  onDeadlinePassed,
  disabled = false,
}: Step3DocumentsProps) {
  const { toast } = useToast();
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [showNotesError, setShowNotesError] = useState(false);

  const notes = state.companyInfo.vendor_notes;
  const notesError =
    notes.length > MAX_NOTES_LENGTH
      ? `Notes must be ${MAX_NOTES_LENGTH} characters or fewer.`
      : undefined;

  function handleNext() {
    if (notesError) {
      setShowNotesError(true);
      return;
    }
    onNext();
  }

  async function handleFilesSelected(files: File[]) {
    setUploadError(null);
    if (disabled) {
      toast({
        variant: 'danger',
        message: 'The bid deadline has passed — uploads are locked.',
      });
      return;
    }
    let submissionId: string;
    try {
      submissionId = await ensureSubmissionId();
    } catch (err) {
      if (err instanceof PortalApiError && err.code === 'DEADLINE_PASSED') {
        onDeadlinePassed();
        return;
      }
      toast({ variant: 'danger', message: 'Could not start a draft. Please try again.' });
      return;
    }

    for (const file of files) {
      try {
        const attachment = await uploadAttachment(submissionId, file);
        onAddAttachment(attachment);
        toast({
          variant: 'success',
          message: `Uploaded ${file.name}`,
        });
      } catch (err) {
        if (err instanceof PortalApiError && err.code === 'DEADLINE_PASSED') {
          onDeadlinePassed();
          return;
        }
        const detail =
          err instanceof PortalApiError ? err.message : `Failed to upload ${file.name}`;
        toast({ variant: 'danger', message: detail });
      }
    }
  }

  async function handleRemove(attachmentId: string) {
    if (disabled) return;
    const submissionId = state.submissionId;
    if (!submissionId) {
      // No draft yet — attachment must be a local-only remnant; drop it.
      onRemoveAttachment(attachmentId);
      return;
    }
    try {
      await deleteAttachment(submissionId, attachmentId);
      onRemoveAttachment(attachmentId);
    } catch (err) {
      if (err instanceof PortalApiError && err.code === 'DEADLINE_PASSED') {
        onDeadlinePassed();
        return;
      }
      toast({ variant: 'danger', message: 'Could not remove attachment. Please try again.' });
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <Card title="Notes to Owner" padding="md">
        <FormField
          label="Optional cover notes"
          required={false}
          hint={`${notes.length} / ${MAX_NOTES_LENGTH} characters`}
          error={showNotesError ? notesError : undefined}
        >
          <TextareaFallback
            value={notes}
            maxLength={MAX_NOTES_LENGTH}
            onChange={(e) => onUpdateNotes(e.target.value)}
            placeholder="Assumptions, exclusions, alternates, scheduling notes, etc."
          />
        </FormField>
      </Card>

      <Card
        title="Your Attachments"
        subtitle="Upload your bid proposal, certificates, and any alternate pricing"
        padding="md"
      >
        <FileUpload
          accept={ACCEPT_TYPES}
          maxSizeMB={MAX_FILE_SIZE_MB}
          multiple
          onFilesSelected={handleFilesSelected}
          onError={(msg) => setUploadError(msg)}
          label="Drag and drop files here, or click to browse"
          hint="PDF, JPEG, or PNG · up to 10 MB each"
        />
        {uploadError && (
          <div className="mt-3">
            <Alert variant="danger">{uploadError}</Alert>
          </div>
        )}

        {state.attachments.length > 0 && (
          <ul className="mt-4 divide-y divide-secondary-100 rounded-md border border-secondary-200">
            {state.attachments.map((att) => (
              <li
                key={att.id}
                className="flex items-center gap-3 px-3 py-2 text-sm"
              >
                <svg
                  viewBox="0 0 20 20"
                  fill="currentColor"
                  className="h-5 w-5 shrink-0 text-success-600"
                  aria-hidden="true"
                >
                  <path
                    fillRule="evenodd"
                    d="M16.704 5.29a1 1 0 010 1.42l-8 8a1 1 0 01-1.42 0l-4-4a1 1 0 011.42-1.42L8 12.58l7.29-7.29a1 1 0 011.41 0z"
                    clipRule="evenodd"
                  />
                </svg>
                <div className="min-w-0 flex-1">
                  <p className="truncate font-medium text-secondary-900">{att.name}</p>
                  <p className="text-xs text-secondary-500">{formatBytes(att.size)}</p>
                </div>
                <button
                  type="button"
                  onClick={() => handleRemove(att.id)}
                  aria-label={`Remove ${att.name}`}
                  disabled={disabled}
                  className="rounded-md p-1 text-secondary-400 hover:bg-secondary-100 hover:text-danger-600 focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:outline-none disabled:cursor-not-allowed disabled:opacity-50"
                >
                  <svg viewBox="0 0 20 20" fill="currentColor" className="h-4 w-4">
                    <path d="M6.28 5.22a.75.75 0 00-1.06 1.06L8.94 10l-3.72 3.72a.75.75 0 101.06 1.06L10 11.06l3.72 3.72a.75.75 0 101.06-1.06L11.06 10l3.72-3.72a.75.75 0 00-1.06-1.06L10 8.94 6.28 5.22z" />
                  </svg>
                </button>
              </li>
            ))}
          </ul>
        )}

        <p className="mt-3 text-xs text-secondary-500">
          Attachments are optional. Files upload directly to secure storage.
        </p>
      </Card>

      <div className="flex flex-col-reverse items-stretch gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex flex-col-reverse gap-3 sm:flex-row sm:gap-2">
          <Button type="button" variant="ghost" onClick={onBack}>
            ← Back
          </Button>
          <Button type="button" variant="outline" onClick={onSaveDraft}>
            Save Draft
          </Button>
        </div>
        <Button type="button" variant="primary" onClick={handleNext}>
          Next: Review →
        </Button>
      </div>
    </div>
  );
}

/**
 * Simple textarea styled to match TextInput. The shared UI library
 * doesn't ship a Textarea component today, and adding one is out of
 * scope for Task 5.1.
 */
function TextareaFallback({
  value,
  onChange,
  maxLength,
  placeholder,
}: {
  value: string;
  onChange: (e: React.ChangeEvent<HTMLTextAreaElement>) => void;
  maxLength?: number;
  placeholder?: string;
}) {
  return (
    <textarea
      value={value}
      onChange={onChange}
      rows={5}
      maxLength={maxLength}
      placeholder={placeholder}
      className="w-full rounded-lg border border-secondary-300 bg-white px-3 py-2 text-sm text-secondary-900 placeholder:text-secondary-400 focus:border-primary-500 focus:ring-2 focus:ring-primary-500/20 focus:outline-none"
    />
  );
}
