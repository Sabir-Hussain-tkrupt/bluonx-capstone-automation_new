import { useState } from 'react';
import { FileText } from 'lucide-react';
import { Button, Card, FormField, TextInput, useToast } from '@/components/ui';
import { useBidContext } from '../../hooks/useBidContext';
import { downloadProjectDocument } from '../../services/portalApi';
import { signatureMatches } from '../../utils/attestation';
import { ProjectContextPanel } from '../ProjectContextPanel';

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export interface Step1CompanyInfoProps {
  onNext: () => void;
  onSaveDraft: () => void;
  /** Vendor's proposed start date (Task 8.1.5). ISO date string or null. */
  proposedStartDate: string | null;
  /** Sent on every keystroke — empty string is normalized to null. */
  onUpdateProposedStartDate: (value: string | null) => void;
  /** Vendor's typed CAPS SoW attestation. */
  sowAttestedName: string;
  /** Sent on every keystroke; the reducer auto-uppercases. */
  onUpdateSowAttestation: (value: string) => void;
}

export function Step1CompanyInfo({
  onNext,
  onSaveDraft,
  proposedStartDate,
  onUpdateProposedStartDate,
  sowAttestedName,
  onUpdateSowAttestation,
}: Step1CompanyInfoProps) {
  const { vendor, project, task, bid_package, project_documents } = useBidContext();
  const { toast } = useToast();
  const [attempted, setAttempted] = useState(false);
  const requiredStart = !!bid_package.desired_start_date;
  // Signature must match the vendor's company name. Only surface the error
  // once the vendor has typed something (don't shout on an untouched field)
  // or once they've tried to advance.
  const sigTouched = sowAttestedName.trim().length > 0;
  const sigMatches = signatureMatches(sowAttestedName, vendor.company_name);
  // Gate "Next" like Steps 2/3 do: the SoW signature is always required and
  // the proposed start date is required when the package sets a desired date.
  const startMissing = requiredStart && !proposedStartDate;
  const canProceed = sigMatches && !startMissing;

  function handleNext() {
    setAttempted(true);
    if (!canProceed) return;
    onNext();
  }

  async function handleDownload(documentId: string, fileName: string) {
    try {
      const url = await downloadProjectDocument(documentId);
      // Signed URLs from FastAPI expire in ~1h. Opening in a new tab
      // lets the browser fetch the blob directly from Supabase Storage
      // without leaving the bid form. `noopener,noreferrer` prevents
      // the opened tab from getting a window.opener back to the portal.
      window.open(url, '_blank', 'noopener,noreferrer');
      toast({ variant: 'info', message: `Opening ${fileName}…` });
    } catch {
      toast({ variant: 'danger', message: 'Could not start download.' });
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <Card title="Your Company" subtitle="Contact details on file with BluOnX" padding="md">
        <dl className="grid gap-4 sm:grid-cols-2">
          <div>
            <dt className="text-xs font-medium tracking-wide text-secondary-500 uppercase">
              Company Name
            </dt>
            <dd className="mt-1 text-sm font-semibold text-secondary-900">
              {vendor.company_name}
            </dd>
          </div>
          <div>
            <dt className="text-xs font-medium tracking-wide text-secondary-500 uppercase">
              Primary Contact
            </dt>
            <dd className="mt-1 text-sm font-semibold text-secondary-900">
              {vendor.primary_contact_name}
            </dd>
          </div>
          <div>
            <dt className="text-xs font-medium tracking-wide text-secondary-500 uppercase">
              Email
            </dt>
            <dd className="mt-1 break-all text-sm text-secondary-700">{vendor.email}</dd>
          </div>
          <div>
            <dt className="text-xs font-medium tracking-wide text-secondary-500 uppercase">
              Phone
            </dt>
            <dd className="mt-1 text-sm text-secondary-700">{vendor.phone ?? '—'}</dd>
          </div>
        </dl>
        <p className="mt-4 text-xs text-secondary-500">
          If any of this is wrong, please contact the BluOnX. These fields
          are locked during bid submission.
        </p>
      </Card>

      <ProjectContextPanel project={project} task={task} bidPackage={bid_package} />

      <Card
        title="Project Timing"
        subtitle={
          requiredStart
            ? 'Required: the project manager has set a target start date for this bid'
            : 'Optional: when you could realistically begin work'
        }
        padding="md"
      >
        <FormField
          label="Proposed start date"
          htmlFor="proposed-start-date"
          required={requiredStart}
          error={
            attempted && startMissing ? 'Proposed start date is required.' : undefined
          }
          hint={
            requiredStart
              ? 'Pre-filled with the desired date; change it if you cannot hit that target.'
              : 'If you have a target start in mind, share it here.'
          }
        >
          <TextInput
            type="date"
            id="proposed-start-date"
            value={proposedStartDate ?? ''}
            required={requiredStart}
            error={attempted && startMissing}
            onChange={(e) => {
              const v = e.target.value;
              onUpdateProposedStartDate(v === '' ? null : v);
            }}
          />
        </FormField>
      </Card>

      <Card
        title="Scope of Work"
        subtitle="Review the Scope of Work and attest that your bid reflects it"
        padding="md"
      >
        {bid_package.scope_of_work_document_id ? (
          <div className="mb-4 flex items-center justify-between gap-3 rounded-md border border-secondary-200 bg-secondary-50 px-4 py-3">
            <div className="min-w-0">
              <p className="truncate text-sm font-medium text-secondary-900">
                {bid_package.scope_of_work_file_name ?? 'Scope of Work'}
              </p>
              <p className="text-xs text-secondary-500">Provided by the project manager</p>
            </div>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() =>
                handleDownload(
                  bid_package.scope_of_work_document_id as string,
                  bid_package.scope_of_work_file_name ?? 'Scope of Work',
                )
              }
            >
              Download
            </Button>
          </div>
        ) : (
          <p className="mb-4 text-sm text-secondary-500">
            No Scope of Work document is available for this package.
          </p>
        )}

        <FormField
          label={`Sign by typing your company name (${vendor.company_name})`}
          htmlFor="sow-attestation"
          required
          hint="Type your company name exactly as shown to confirm you have reviewed the Scope of Work and your bid reflects it."
          error={
            (sigTouched || attempted) && !sigMatches
              ? sigTouched
                ? 'This must exactly match your company name to sign.'
                : 'Please sign by typing your company name to attest to the Scope of Work.'
              : undefined
          }
        >
          <TextInput
            id="sow-attestation"
            required
            autoComplete="off"
            placeholder={vendor.company_name.toUpperCase()}
            value={sowAttestedName}
            error={(sigTouched || attempted) && !sigMatches}
            onChange={(e) => onUpdateSowAttestation(e.target.value)}
          />
        </FormField>
      </Card>

      <Card
        title="Project Documents"
        subtitle="Reference drawings and reports for this bid"
        padding="md"
      >
        {project_documents.length === 0 ? (
          <p className="text-sm text-secondary-500">No project documents attached.</p>
        ) : (
          <ul className="divide-y divide-secondary-100">
            {project_documents.map((doc) => (
              <li key={doc.id} className="flex items-center gap-3 py-3">
                <div
                  aria-hidden="true"
                  className="flex h-10 w-10 shrink-0 items-center justify-center rounded-md bg-primary-50 text-primary-600"
                >
                  <FileText className="h-5 w-5" aria-hidden="true" />
                </div>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium text-secondary-900">
                    {doc.file_name}
                  </p>
                  <p className="text-xs text-secondary-500">
                    {formatBytes(doc.file_size_bytes)}
                  </p>
                </div>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => handleDownload(doc.id, doc.file_name)}
                >
                  Download
                </Button>
              </li>
            ))}
          </ul>
        )}
      </Card>

      <div className="flex flex-col-reverse items-stretch gap-3 sm:flex-row sm:items-center sm:justify-between">
        <Button type="button" variant="outline" onClick={onSaveDraft}>
          Save Draft
        </Button>
        <Button type="button" variant="primary" onClick={handleNext}>
          Next: Pricing →
        </Button>
      </div>
    </div>
  );
}
