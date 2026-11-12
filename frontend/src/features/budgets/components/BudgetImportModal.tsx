import { useState } from 'react';
import { Modal } from '@/components/ui/Modal';
import { Button } from '@/components/ui/Button';
import { FileUpload } from '@/components/ui/FileUpload';
import { Alert } from '@/components/ui/Alert';
import { StatusBadge } from '@/components/ui/StatusBadge';
import { useToast } from '@/components/ui/Toast';
import { errorMessage } from '@/lib/api';
import { useApplyBudgetImport, usePreviewBudgetImport } from '../hooks/useBudget';
import type { ImportPreview } from '../types';
import { formatMoney } from '../utils/money';

interface BudgetImportModalProps {
  projectId: string;
  isOpen: boolean;
  onClose: () => void;
}

const ACTION_VARIANT = { update: 'info', add: 'success', error: 'danger' } as const;

/**
 * Task 2.8 — load an early budget from Excel / CSV into a DRAFT budget.
 * Step 1 previews (nothing written), step 2 applies the valid rows in one
 * transaction. Rows are matched to existing lines by name.
 */
export function BudgetImportModal({ projectId, isOpen, onClose }: BudgetImportModalProps) {
  const { toast } = useToast();
  const previewMutation = usePreviewBudgetImport(projectId);
  const applyMutation = useApplyBudgetImport(projectId);
  const [file, setFile] = useState<File | null>(null);
  const [fileError, setFileError] = useState('');
  const [preview, setPreview] = useState<ImportPreview | null>(null);
  const [error, setError] = useState<string | null>(null);

  const isPending = previewMutation.isPending || applyMutation.isPending;
  const validRows = preview?.rows.filter((r) => r.action !== 'error') ?? [];

  const reset = () => {
    setFile(null);
    setFileError('');
    setPreview(null);
    setError(null);
  };

  const close = () => {
    if (isPending) return;
    reset();
    onClose();
  };

  const runPreview = () => {
    if (!file) return;
    setError(null);
    previewMutation.mutate(file, {
      onSuccess: setPreview,
      onError: (e) => setError(errorMessage(e, 'The file could not be read.')),
    });
  };

  const apply = () => {
    applyMutation.mutate(validRows, {
      onSuccess: (res) => {
        toast({ variant: 'success', message: `Import applied: ${res.updated} updated, ${res.added} added.` });
        reset();
        onClose();
      },
      onError: (e) => setError(errorMessage(e, 'The import could not be applied.')),
    });
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={close}
      title="Import budget"
      size="xl"
      footer={
        <>
          <Button variant="ghost" onClick={close} disabled={isPending}>Cancel</Button>
          {preview ? (
            <Button onClick={apply} isLoading={applyMutation.isPending} disabled={validRows.length === 0}>
              Apply {validRows.length} change{validRows.length === 1 ? '' : 's'}
            </Button>
          ) : (
            <Button onClick={runPreview} isLoading={previewMutation.isPending} disabled={!file}>Preview</Button>
          )}
        </>
      }
    >
      <div className="space-y-4">
        {error && <Alert variant="danger" title="Import failed">{error}</Alert>}

        {!preview && (
          <>
            <p className="text-sm text-secondary-600">
              Upload an Excel (.xlsx) or CSV file with at least a <strong>Line</strong> (or Description) column and an{' '}
              <strong>Amount</strong> (or Budget) column. Optional columns: Section, Type, Start, End, Payment terms,
              Cash bucket. Rows are matched to existing lines by name; new names become new lines.
            </p>
            <FileUpload
              accept=".csv,.xlsx"
              maxSizeMB={2}
              onFilesSelected={(files) => {
                setFile(files[0] ?? null);
                setFileError('');
              }}
              onError={setFileError}
              error={fileError}
              uploading={previewMutation.isPending}
              hint="Excel (.xlsx) or CSV up to 2MB"
              onRemoveFile={() => setFile(null)}
            />
          </>
        )}

        {preview && (
          <>
            <div className="flex flex-wrap items-center gap-3 text-sm">
              <span className="text-secondary-500">Update: <strong className="text-secondary-900">{preview.summary.update}</strong></span>
              <span className="text-secondary-300">|</span>
              <span className="text-secondary-500">Add: <strong className="text-secondary-900">{preview.summary.add}</strong></span>
              <span className="text-secondary-300">|</span>
              <span className={preview.summary.error ? 'font-semibold text-danger-600' : 'text-secondary-500'}>
                Errors: <strong>{preview.summary.error}</strong>
              </span>
            </div>
            {preview.summary.error > 0 && (
              <Alert variant="warning" title="Some rows will be skipped">
                Rows with errors are not imported. Fix them in the file and import again, or apply the valid rows now.
              </Alert>
            )}
            <div className="max-h-[50vh] overflow-auto rounded-lg border border-secondary-200">
              <table className="w-full text-left text-sm">
                <thead className="sticky top-0 bg-white">
                  <tr className="border-b border-secondary-200">
                    <th className="px-4 py-3 font-medium text-secondary-500">Row</th>
                    <th className="px-4 py-3 font-medium text-secondary-500">Line</th>
                    <th className="px-4 py-3 text-right font-medium text-secondary-500">Current</th>
                    <th className="px-4 py-3 text-right font-medium text-secondary-500">New amount</th>
                    <th className="px-4 py-3 font-medium text-secondary-500">Result</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-secondary-100">
                  {preview.rows.map((r) => (
                    <tr key={r.row_number} className={r.action === 'error' ? 'bg-danger-50/40' : undefined}>
                      <td className="px-4 py-3 text-secondary-500">{r.row_number}</td>
                      <td className="px-4 py-3">
                        <div className="font-medium text-secondary-900">{r.name}</div>
                        {[...r.errors, ...r.warnings].map((m) => (
                          <div key={m} className={`text-xs ${r.errors.includes(m) ? 'text-danger-600' : 'text-warning-600'}`}>{m}</div>
                        ))}
                      </td>
                      <td className="px-4 py-3 text-right tabular-nums">{r.current_amount != null ? formatMoney(r.current_amount) : '—'}</td>
                      <td className="px-4 py-3 text-right tabular-nums">{r.budget_amount != null ? formatMoney(r.budget_amount) : '—'}</td>
                      <td className="px-4 py-3">
                        <StatusBadge status={r.action} variant={ACTION_VARIANT[r.action]} size="sm" />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
      </div>
    </Modal>
  );
}
