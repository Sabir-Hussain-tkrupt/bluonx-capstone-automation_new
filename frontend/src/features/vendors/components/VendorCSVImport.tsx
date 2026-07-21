import { useState, useMemo, useCallback, useRef } from 'react';
import Papa from 'papaparse';
import { CheckCircle2, FileText, UploadCloud } from 'lucide-react';
import { Modal } from '@/components/ui/Modal';
import { Button } from '@/components/ui/Button';
import { Select } from '@/components/ui/Select';
import { StatusBadge } from '@/components/ui/StatusBadge';
import { useImportVendors } from '@/features/vendors/hooks/useImportVendors';
import { useToast } from '@/components/ui/Toast/useToast';
import type { VendorImportRow, VendorImportResponse } from '@/features/vendors/api/vendor.mutations';
import type { StatusVariant } from '@/components/ui/types';
import { isValidEmail } from '@/utils/validation';

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

/**
 * Must match VENDOR_IMPORT_MAX_ROWS in backend/app/models/vendors.py.
 *
 * The server imports row by row, geocoding each address, so a larger batch
 * outlives the request timeout: the user is told the import failed while rows
 * keep being created behind them.
 */
const MAX_IMPORT_ROWS = 100;

/** Papa error codes that mean a single row is malformed rather than the file. */
const ROW_SCOPED_PARSE_CODES = new Set([
  'TooFewFields',
  'TooManyFields',
  'MissingQuotes',
  'InvalidQuotes',
]);

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

  // Per-row problems found by the CSV parser itself, keyed by row index.
  const [parseErrors, setParseErrors] = useState<Record<number, string[]>>({});
  // A problem with the file as a whole; blocks leaving the upload step.
  const [fileError, setFileError] = useState('');

  // Map step
  const [columnMapping, setColumnMapping] = useState<Record<string, string>>({});

  // Confirm step
  const [importResult, setImportResult] = useState<VendorImportResponse | null>(null);
  // Original CSV line for each row in the submitted batch, by position. The
  // server numbers its errors over the array it received, which excludes rows
  // we filtered out, so those numbers have to be mapped back before display.
  const [submittedLines, setSubmittedLines] = useState<number[]>([]);

  const resetState = useCallback(() => {
    setStep('upload');
    setFileName('');
    setCsvHeaders([]);
    setCsvRows([]);
    setColumnMapping({});
    setImportResult(null);
    setParseErrors({});
    setFileError('');
    setSubmittedLines([]);
  }, []);

  const handleClose = () => {
    resetState();
    onClose();
  };

  // ─── Upload Step ──────────────────────────────────────────────

  const handleFileSelect = (file: File) => {
    setFileName(file.name);
    setFileError('');
    setParseErrors({});

    Papa.parse(file, {
      header: true,
      skipEmptyLines: true,
      complete: (results) => {
        const headers = results.meta.fields ?? [];
        const rows = results.data as Record<string, string>[];

        // File-level problems: the parse itself is untrustworthy, so every row
        // below it would be misaligned. Refuse rather than show a confident
        // preview of garbage.
        const normalizedHeaders = headers.map((h) => h.trim().toLowerCase());
        if (headers.length === 0) {
          setFileError('No columns could be detected. Check that the first row contains column headers.');
          return;
        }
        if (normalizedHeaders.some((h) => !h)) {
          setFileError('One or more columns have a blank header. Name every column and try again.');
          return;
        }
        if (new Set(normalizedHeaders).size !== normalizedHeaders.length) {
          setFileError('Two or more columns share the same header. Give each column a unique name.');
          return;
        }
        if (results.errors.some((e) => e.code === 'UndetectableDelimiter')) {
          setFileError('The column separator could not be detected. Save the file as a standard comma-separated CSV.');
          return;
        }
        if (rows.length === 0) {
          setFileError('This file has headers but no data rows.');
          return;
        }
        if (rows.length > MAX_IMPORT_ROWS) {
          setFileError(
            `This file has ${rows.length} rows. Imports are limited to ${MAX_IMPORT_ROWS} rows at a time — split the file and import it in parts.`,
          );
          return;
        }

        // Row-level parse problems are hard errors, not warnings: a row with
        // the wrong field count has shifted every value into the wrong column,
        // so importing it would create real garbage.
        const byRow: Record<number, string[]> = {};
        results.errors.forEach((e) => {
          if (typeof e.row === 'number' && ROW_SCOPED_PARSE_CODES.has(e.code ?? '')) {
            byRow[e.row] = [...(byRow[e.row] ?? []), e.message || 'Malformed CSV row'];
          }
        });
        setParseErrors(byRow);

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
      // Parser-level problems come first: if the row didn't parse cleanly,
      // nothing else about it can be trusted.
      const errors: string[] = [...(parseErrors[index] ?? [])];
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
      if (r.contact_email && !isValidEmail(r.contact_email)) {
        errors.push('Invalid email format');
      }

      return { row: r, index, errors, warnings };
    });
  }, [mappedRows, parseErrors]);

  // Two columns pointing at the same vendor field silently overwrite each
  // other during mapping, so the user needs to be told which one wins.
  const duplicateTargets = useMemo(() => {
    const seen = new Set<string>();
    const dupes = new Set<string>();
    Object.values(columnMapping).forEach((target) => {
      if (!target) return;
      if (seen.has(target)) dupes.add(target);
      seen.add(target);
    });
    return dupes;
  }, [columnMapping]);

  const validCount = validatedRows.filter((r) => r.errors.length === 0).length;
  const errorCount = validatedRows.filter((r) => r.errors.length > 0).length;
  const warningCount = validatedRows.filter((r) => r.warnings.length > 0 && r.errors.length === 0).length;

  // ─── Confirm & Import Step ────────────────────────────────────

  const handleImport = async () => {
    const importable = validatedRows.filter((r) => r.errors.length === 0);
    const validRows = importable.map((r) => r.row as unknown as VendorImportRow);

    // Record which CSV line each submitted row came from. The server numbers
    // its errors 1-based over the array it receives, and that array has the
    // invalid rows stripped out, so without this map every reported row number
    // points at the wrong line in the user's file.
    setSubmittedLines(importable.map((r) => r.index + 1));

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
    <Modal
      isOpen={isOpen}
      onClose={handleClose}
      title={stepTitle}
      size="xl"
      // Losing a mapped file to a misplaced click means redoing the upload
      // and every column mapping.
      closeOnOverlayClick={false}
    >
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
      {step === 'upload' && fileError && (
        <div className="mb-4 rounded-lg border border-danger-200 bg-danger-50 px-4 py-3">
          <p className="text-sm font-medium text-danger-800">
            {fileName ? `Could not use ${fileName}` : 'Could not use this file'}
          </p>
          <p className="mt-1 text-sm text-danger-700">{fileError}</p>
        </div>
      )}
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
          <UploadCloud className="mb-4 h-12 w-12 text-secondary-400" aria-hidden="true" />
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
            <FileText className="h-5 w-5 text-secondary-500" aria-hidden="true" />
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
            {duplicateTargets.size > 0 && (
              <p className="mt-2 text-sm text-warning-700">
                More than one column is mapped to the same field
                {' '}
                ({[...duplicateTargets]
                  .map((t) => TARGET_FIELDS.find((f) => f.value === t)?.label ?? t)
                  .join(', ')}
                ). Only the last mapped column will be imported.
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
            {/* This discards the file and every column mapping, so it is not
                a "back" step. Named for what it does. */}
            <Button variant="ghost" onClick={() => { resetState(); }}>
              Start Over
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
            <CheckCircle2 className="mx-auto mb-3 h-10 w-10 text-success-600" aria-hidden="true" />
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
                  <li key={i}>
                    Row {submittedLines[err.row - 1] ?? err.row}: {err.message}
                  </li>
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
