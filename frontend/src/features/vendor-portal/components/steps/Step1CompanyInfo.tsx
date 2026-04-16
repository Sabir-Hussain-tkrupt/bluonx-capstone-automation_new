import { Button, Card, useToast } from '@/components/ui';
import { useBidContext } from '../../hooks/useBidContext';
import { downloadProjectDocument } from '../../services/portalApi';
import { ProjectContextPanel } from '../ProjectContextPanel';

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export interface Step1CompanyInfoProps {
  onNext: () => void;
  onSaveDraft: () => void;
}

export function Step1CompanyInfo({
  onNext,
  onSaveDraft,
}: Step1CompanyInfoProps) {
  const { vendor, project, task, bid_package, project_documents } = useBidContext();
  const { toast } = useToast();

  async function handleDownload(documentId: string, fileName: string) {
    try {
      await downloadProjectDocument(documentId);
      toast({
        variant: 'info',
        message: `Download started: ${fileName} (mock — real signed URL in Task 5.3)`,
      });
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
                  <svg viewBox="0 0 20 20" fill="currentColor" className="h-5 w-5">
                    <path
                      fillRule="evenodd"
                      d="M4 4a2 2 0 012-2h6l4 4v10a2 2 0 01-2 2H6a2 2 0 01-2-2V4zm8 0v2h2l-2-2z"
                      clipRule="evenodd"
                    />
                  </svg>
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
        <Button type="button" variant="primary" onClick={onNext}>
          Next: Pricing →
        </Button>
      </div>
    </div>
  );
}
