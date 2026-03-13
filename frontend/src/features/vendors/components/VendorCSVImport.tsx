import { useState, useMemo, useCallback, useRef } from 'react';
import Papa from 'papaparse';
import { Modal } from '@/components/ui/Modal';
import { Button } from '@/components/ui/Button';
import { Select } from '@/components/ui/Select';
import { StatusBadge } from '@/components/ui/StatusBadge';
import { useImportVendors } from '@/features/vendors/hooks/useImportVendors';
import { useToast } from '@/components/ui/Toast/useToast';
import type { VendorImportRow, VendorImportResponse } from '@/features/vendors/api/vendor.mutations';
import type { StatusVariant } from '@/components/ui/types';

interface VendorCSVImportProps {
  isOpen: boolean;
  onClose: () => void;
}

type Step = 'upload' | 'map' | 'confirm';

// Vendor field targets for CSV column mapping
const TARGET_FIELDS = [
  { value: '', label: '— Skip —' },
  { value: 'company_name', label: 'Company Name *' },
  { value: 'address', label: 'Address' },
  { value: 'city', label: 'City' },
  { value: 'state', label: 'State' },
  { value: 'zip_code', label: 'ZIP Code' },
  { value: 'contact_name', label: 'Contact Name' },
  { value: 'contact_email', label: 'Contact Email' },
  { value: 'contact_phone', label: 'Contact Phone' },
  { value: 'contact_title', label: 'Contact Title' },
  { value: 'notes', label: 'Notes' },
];

// Auto-detect CSV headers → vendor fields
const HEADER_MAP: Record<string, string> = {
  company_name: 'company_name',
  company: 'company_name',
  'company name': 'company_name',
  vendor: 'company_name',
  'vendor name': 'company_name',
  name: 'company_name',
  address: 'address',
  'street address': 'address',
  street: 'address',
  city: 'city',
  state: 'state',
  st: 'state',
  zip: 'zip_code',
  zip_code: 'zip_code',
  'zip code': 'zip_code',
  zipcode: 'zip_code',
  postal: 'zip_code',
  'postal code': 'zip_code',
  contact: 'contact_name',
  contact_name: 'contact_name',
  'contact name': 'contact_name',
  'primary contact': 'contact_name',
  email: 'contact_email',
  contact_email: 'contact_email',
  'contact email': 'contact_email',
  phone: 'contact_phone',
  contact_phone: 'contact_phone',
  'contact phone': 'contact_phone',
  telephone: 'contact_phone',
  title: 'contact_title',
  contact_title: 'contact_title',
  'contact title': 'contact_title',
  'job title': 'contact_title',
  notes: 'notes',
  note: 'notes',
  comments: 'notes',
};

interface RowValidation {
  row: Record<string, string>;
  index: number;
  errors: string[];
  warnings: string[];
}

const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export function VendorCSVImport({ isOpen, onClose }: VendorCSVImportProps) {
  const { toast } = useToast();
  const importMutation = useImportVendors();
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Step state
  const [step, setStep] = useState<Step>('upload');

  // Upload step
  const [fileName, setFileName] = useState('');
  const [csvHeaders, setCsvHeaders] = useState<string[]>([]);
  const [csvRows, setCsvRows] = useState<Record<string, string>[]>([]);

  // Map step
  const [columnMapping, setColumnMapping] = useState<Record<string, string>>({});

  // Confirm step
  const [importResult, setImportResult] = useState<VendorImportResponse | null>(null);

  const resetState = useCallback(() => {
    setStep('upload');
    setFileName('');
    setCsvHeaders([]);
    setCsvRows([]);
    setColumnMapping({});
    setImportResult(null);
  }, []);

  const handleClose = () => {
    resetState();
    onClose();
  };

  // ─── Upload Step ──────────────────────────────────────────────

  const handleFileSelect = (file: File) => {
    setFileName(file.name);

    Papa.parse(file, {
      header: true,
      skipEmptyLines: true,
      complete: (results) => {
        const headers = results.meta.fields ?? [];
        const rows = results.data as Record<string, string>[];

        setCsvHeaders(headers);
        setCsvRows(rows);

        // Auto-detect column mappings
        const autoMapping: Record<string, string> = {};
        headers.forEach((header) => {
          const normalized = header.trim().toLowerCase();
          if (HEADER_MAP[normalized]) {
            autoMapping[header] = HEADER_MAP[normalized];
          }
        });
        setColumnMapping(autoMapping);
        setStep('map');
      },
      error: () => {
        toast({ variant: 'danger', message: 'Failed to parse CSV file. Please check the format.' });
      },
    });
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    const file = e.dataTransfer.files[0];
    if (file && (file.name.endsWith('.csv') || file.type === 'text/csv')) {
      handleFileSelect(file);
    } else {
      toast({ variant: 'danger', message: 'Please upload a .csv file.' });
    }
  };

  const handleFileInput = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) handleFileSelect(file);
  };

  // ─── Map & Validate Step ──────────────────────────────────────

  const updateMapping = (csvHeader: string, targetField: string) => {
    setColumnMapping((prev) => ({ ...prev, [csvHeader]: targetField }));
  };

  const hasCompanyNameMapped = useMemo(
    () => Object.values(columnMapping).includes('company_name'),
    [columnMapping],
  );

  // Transform CSV rows using the column mapping
  const mappedRows: VendorImportRow[] = useMemo(() => {
    return csvRows.map((row) => {
      const mapped: Record<string, string> = {};
      Object.entries(columnMapping).forEach(([csvHeader, targetField]) => {
        if (targetField && row[csvHeader]) {
          mapped[targetField] = row[csvHeader].trim();
        }
      });
      return mapped as unknown as VendorImportRow;
    });
  }, [csvRows, columnMapping]);

  // Validate each row
  const validatedRows: RowValidation[] = useMemo(() => {
    const companyNames = new Set<string>();

    return mappedRows.map((row, index) => {
      const errors: string[] = [];
      const warnings: string[] = [];
      const r = row as unknown as Record<string, string>;

      // Required: company_name
      if (!r.company_name) {
        errors.push('Company name is required');
      } else {
        const lower = r.company_name.toLowerCase();
        if (companyNames.has(lower)) {
          warnings.push('Duplicate company name in CSV');
        }
        companyNames.add(lower);
      }

      // Validate email if provided
      if (r.contact_email && !emailRegex.test(r.contact_email)) {
        errors.push('Invalid email format');
      }

      return { row: r, index, errors, warnings };
    });
  }, [mappedRows]);

  const validCount = validatedRows.filter((r) => r.errors.length === 0).length;
  const errorCount = validatedRows.filter((r) => r.errors.length > 0).length;
  const warningCount = validatedRows.filter((r) => r.warnings.length > 0 && r.errors.length === 0).length;

  // ─── Confirm & Import Step ────────────────────────────────────

  const handleImport = async () => {
    const validRows = validatedRows
      .filter((r) => r.errors.length === 0)
      .map((r) => r.row as unknown as VendorImportRow);

    importMutation.mutate(validRows, {
      onSuccess: (data) => {
        setImportResult(data);
        toast({ variant: 'success', message: `${data.created} vendor(s) imported successfully.` });
      },
      onError: (error) => {
        toast({
          variant: 'danger',
          message: (error as { message?: string }).message || 'Import failed.',
        });
      },
    });
  };

  // ─── Step Title ───────────────────────────────────────────────

  const stepTitle = step === 'upload'
    ? 'Import Vendors — Upload CSV'
    : step === 'map'
      ? 'Import Vendors — Map & Validate'
      : 'Import Vendors — Confirm';

  return (
    <Modal isOpen={isOpen} onClose={handleClose} title={stepTitle} size="xl">
      {/* Step Indicator */}
      <div className="mb-6 flex items-center justify-between sm:justify-start sm:gap-2">
        {(['upload', 'map', 'confirm'] as Step[]).map((s, i) => (
          <div key={s} className="flex items-center gap-1.5 sm:gap-2">
            <div
              className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-xs font-semibold ${
                step === s
                  ? 'bg-primary-600 text-white'
                  : i < ['upload', 'map', 'confirm'].indexOf(step)
                    ? 'bg-primary-100 text-primary-700'
                    : 'bg-secondary-100 text-secondary-500'
              }`}
            >
              {i + 1}
            </div>
            <span className={`text-xs sm:text-sm ${step === s ? 'font-medium text-secondary-900' : 'text-secondary-500'}`}>
              {s === 'upload' ? 'Upload' : s === 'map' ? 'Map & Validate' : 'Confirm'}
            </span>
            {i < 2 && <div className="mx-1 hidden h-px w-8 bg-secondary-300 sm:mx-2 sm:block" />}
          </div>
        ))}
      </div>

      {/* ─── Step 1: Upload ──────────────────────────────────── */}
      {step === 'upload' && (
        <div
          role="button"
          tabIndex={0}
          className="flex cursor-pointer flex-col items-center justify-center rounded-lg border-2 border-dashed border-secondary-300 p-6 text-center transition-colors hover:border-primary-400 hover:bg-secondary-50 sm:p-12"
          onDragOver={(e) => e.preventDefault()}
          onDrop={handleDrop}
          onClick={() => fileInputRef.current?.click()}
          onKeyDown={(e) => {
            if (e.key === 'Enter' || e.key === ' ') {
              e.preventDefault();
              fileInputRef.current?.click();
            }
          }}
        >
          <svg
            className="mb-4 h-12 w-12 text-secondary-400"
            fill="none"
            viewBox="0 0 24 24"
            strokeWidth={1.5}
            stroke="currentColor"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5m-13.5-9L12 3m0 0l4.5 4.5M12 3v13.5"
            />
          </svg>
          <p className="mb-2 text-sm font-medium text-secondary-700">
            Drag and drop your CSV file here
          </p>
          <p className="mb-4 text-xs text-secondary-500">or click anywhere to browse</p>
          <div className="rounded-lg bg-primary-50 px-4 py-2 text-sm font-medium text-primary-700">
            Choose File
          </div>
          <input
            ref={fileInputRef}
            type="file"
            accept=".csv,text/csv"
            className="hidden"
            onChange={handleFileInput}
          />
          <p className="mt-4 text-xs text-secondary-400">
            Expected columns: Company Name, Address, City, State, ZIP, Contact Name, Email, Phone
          </p>
        </div>
      )}

      {/* ─── Step 2: Map & Validate ──────────────────────────── */}
      {step === 'map' && (
        <div className="space-y-6">
          {/* File info */}
          <div className="flex items-center gap-3 rounded-lg bg-secondary-50 px-4 py-3">
            <svg className="h-5 w-5 text-secondary-500" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m2.25 0H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z" />
            </svg>
            <span className="text-sm font-medium text-secondary-700">{fileName}</span>
            <span className="text-sm text-secondary-500">— {csvRows.length} row(s) detected</span>
          </div>

          {/* Column Mapping */}
          <div>
            <h3 className="mb-3 text-sm font-semibold text-secondary-800">Column Mapping</h3>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              {csvHeaders.map((header) => (
                <div key={header} className="flex flex-col gap-1 sm:flex-row sm:items-center sm:gap-3">
                  <div className="flex items-center gap-2 sm:w-40">
                    <span className="truncate text-sm font-medium text-secondary-700 sm:font-normal" title={header}>
                      {header}
                    </span>
                    <span className="hidden text-secondary-400 sm:inline">→</span>
                  </div>
                  <div className="flex-1">
                    <Select
                      value={columnMapping[header] || ''}
                      onChange={(e) => updateMapping(header, e.target.value)}
                      options={TARGET_FIELDS}
                      size="sm"
                    />
                  </div>
                </div>
              ))}
            </div>
            {!hasCompanyNameMapped && (
              <p className="mt-2 text-sm text-danger-600">
                You must map at least one column to "Company Name".
              </p>
            )}
          </div>

          {/* Validation Summary */}
          <div className="flex gap-4 rounded-lg bg-secondary-50 px-4 py-3">
            <span className="text-sm">
              <span className="font-medium text-success-700">{validCount}</span> valid
            </span>
            {errorCount > 0 && (
              <span className="text-sm">
                <span className="font-medium text-danger-700">{errorCount}</span> error(s)
              </span>
            )}
            {warningCount > 0 && (
              <span className="text-sm">
                <span className="font-medium text-warning-700">{warningCount}</span> warning(s)
              </span>
            )}
          </div>

          {/* Validation Preview Table */}
          <div className="max-h-64 overflow-auto rounded-lg border border-secondary-200">
            <table className="min-w-[600px] w-full text-left text-sm">
              <thead className="sticky top-0 bg-secondary-50">
                <tr>
                  <th className="px-3 py-2 font-medium text-secondary-600">#</th>
                  <th className="px-3 py-2 font-medium text-secondary-600">Status</th>
                  <th className="px-3 py-2 font-medium text-secondary-600">Company Name</th>
                  <th className="px-3 py-2 font-medium text-secondary-600">City</th>
                  <th className="px-3 py-2 font-medium text-secondary-600">Contact</th>
                  <th className="px-3 py-2 font-medium text-secondary-600">Issues</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-secondary-100">
                {validatedRows.map((v) => {
                  const hasError = v.errors.length > 0;
                  const hasWarning = v.warnings.length > 0;
                  let variant: StatusVariant = 'success';
                  let label = 'Valid';
                  if (hasError) { variant = 'danger'; label = 'Error'; }
                  else if (hasWarning) { variant = 'warning'; label = 'Warning'; }

                  return (
                    <tr
                      key={v.index}
                      className={hasError ? 'bg-danger-50/50' : hasWarning ? 'bg-warning-50/50' : ''}
                    >
                      <td className="px-3 py-2 text-secondary-500">{v.index + 1}</td>
                      <td className="px-3 py-2">
                        <StatusBadge status={label.toLowerCase()} variant={variant} />
                      </td>
                      <td className="px-3 py-2">{v.row.company_name || '—'}</td>
                      <td className="px-3 py-2">{v.row.city || '—'}</td>
                      <td className="px-3 py-2">{v.row.contact_name || '—'}</td>
                      <td className="px-3 py-2 text-xs text-secondary-500">
                        {[...v.errors, ...v.warnings].join('; ') || '—'}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          {/* Actions */}
          <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-between">
            <Button variant="ghost" onClick={() => { resetState(); }}>
              Back
            </Button>
            <Button
              onClick={() => setStep('confirm')}
              disabled={!hasCompanyNameMapped || validCount === 0}
            >
              Continue to Confirm
            </Button>
          </div>
        </div>
      )}

      {/* ─── Step 3: Confirm & Import ────────────────────────── */}
      {step === 'confirm' && !importResult && (
        <div className="space-y-6">
          <div className="rounded-lg bg-secondary-50 p-6 text-center">
            <p className="text-lg font-semibold text-secondary-900">
              Ready to import {validCount} vendor(s)
            </p>
            {errorCount > 0 && (
              <p className="mt-1 text-sm text-danger-600">
                {errorCount} row(s) with errors will be skipped.
              </p>
            )}
            <p className="mt-3 text-sm text-secondary-500">
              This will create new vendor records. Existing vendors will not be affected.
            </p>
          </div>

          <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-between">
            <Button variant="ghost" onClick={() => setStep('map')}>
              Back
            </Button>
            <Button onClick={handleImport} isLoading={importMutation.isPending}>
              Import {validCount} Vendor(s)
            </Button>
          </div>
        </div>
      )}

      {/* ─── Import Results ──────────────────────────────────── */}
      {step === 'confirm' && importResult && (
        <div className="space-y-6">
          <div className="rounded-lg bg-success-50 p-6 text-center">
            <svg className="mx-auto mb-3 h-10 w-10 text-success-600" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            <p className="text-lg font-semibold text-success-800">
              {importResult.created} vendor(s) imported successfully
            </p>
          </div>

          {importResult.errors.length > 0 && (
            <div className="rounded-lg border border-danger-200 bg-danger-50 p-4">
              <p className="mb-2 text-sm font-medium text-danger-800">
                {importResult.errors.length} row(s) failed:
              </p>
              <ul className="space-y-1 text-sm text-danger-700">
                {importResult.errors.map((err, i) => (
                  <li key={i}>Row {err.row}: {err.message}</li>
                ))}
              </ul>
            </div>
          )}

          <div className="flex justify-end">
            <Button onClick={handleClose}>Done</Button>
          </div>
        </div>
      )}
    </Modal>
  );
}
