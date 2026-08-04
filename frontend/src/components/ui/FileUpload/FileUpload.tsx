import { useCallback, useId, useRef, useState } from 'react';
import { FileText, UploadCloud, X } from 'lucide-react';
import { cn } from '@/utils/cn';

export interface FileUploadProps {
  accept?: string;
  maxSizeMB?: number;
  multiple?: boolean;
  onFilesSelected: (files: File[]) => void;
  onError?: (message: string) => void;
  disabled?: boolean;
  label?: string;
  hint?: string;
  error?: string;
  /** Show upload-in-progress state (disables dropzone, shows progress) */
  uploading?: boolean;
  /** Upload progress 0–100 */
  uploadProgress?: number;
  /** Allow removing individual files before upload */
  onRemoveFile?: (index: number) => void;
  /**
   * Render the internal list of just-selected files. Default true. Set false
   * when the caller manages and displays its own attachment list (e.g. the
   * bid portal's Step 3), to avoid listing every file twice.
   */
  showFileList?: boolean;
}

/**
 * Whether a file satisfies an `accept` list. Handles both dot-extensions
 * (".pdf") and MIME tokens ("image/png", "image/*"), so every existing caller
 * keeps working. The native `accept` attribute filters only the OS picker;
 * this also covers drag-and-drop, where a disallowed type otherwise slipped
 * through client-side and only failed at the server.
 */
function isAcceptedType(file: File, accept: string): boolean {
  const tokens = accept
    .split(',')
    .map((t) => t.trim().toLowerCase())
    .filter(Boolean);
  if (tokens.length === 0) return true;

  const name = file.name.toLowerCase();
  const type = (file.type || '').toLowerCase();

  return tokens.some((token) => {
    if (token.startsWith('.')) return name.endsWith(token);
    if (token.endsWith('/*')) return type.startsWith(token.slice(0, -1));
    if (token.includes('/')) return type === token;
    return false;
  });
}

export function FileUpload({
  accept,
  maxSizeMB = 10,
  multiple = false,
  onFilesSelected,
  onError,
  disabled = false,
  label = 'Drop files here or click to browse',
  hint,
  error,
  uploading = false,
  uploadProgress,
  onRemoveFile,
  showFileList = true,
}: FileUploadProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [isDragOver, setIsDragOver] = useState(false);
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const componentId = useId();
  const errorId = error ? `${componentId}-error` : undefined;
  const hintId = hint ? `${componentId}-hint` : undefined;

  const isDisabled = disabled || uploading;

  const validateAndSelect = useCallback(
    (files: FileList | null) => {
      if (!files || files.length === 0) return;

      const fileArray = Array.from(files);

      if (accept) {
        const wrongType = fileArray.filter((f) => !isAcceptedType(f, accept));
        if (wrongType.length > 0) {
          onError?.(
            `${wrongType.map((f) => f.name).join(', ')} ${wrongType.length === 1 ? 'is' : 'are'} not an accepted file type. Accepted: ${accept}`,
          );
          return;
        }
      }

      const maxBytes = maxSizeMB * 1024 * 1024;
      const oversized = fileArray.filter((f) => f.size > maxBytes);

      if (oversized.length > 0) {
        onError?.(
          `${oversized.map((f) => f.name).join(', ')} exceed${oversized.length === 1 ? 's' : ''} the ${maxSizeMB}MB limit`,
        );
        return;
      }

      setSelectedFiles(fileArray);
      onFilesSelected(fileArray);
    },
    [accept, maxSizeMB, onFilesSelected, onError],
  );

  const handleRemoveFile = useCallback(
    (index: number) => {
      const updated = selectedFiles.filter((_, i) => i !== index);
      setSelectedFiles(updated);
      onRemoveFile?.(index);
      onFilesSelected(updated);
    },
    [selectedFiles, onRemoveFile, onFilesSelected],
  );

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    if (!isDisabled) setIsDragOver(true);
  };

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(false);
    if (!isDisabled) validateAndSelect(e.dataTransfer.files);
  };

  const handleClick = () => {
    if (!isDisabled) inputRef.current?.click();
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if ((e.key === 'Enter' || e.key === ' ') && !isDisabled) {
      e.preventDefault();
      inputRef.current?.click();
    }
  };

  return (
    <div className="w-full">
      <div
        role="button"
        tabIndex={isDisabled ? -1 : 0}
        aria-describedby={[hintId, errorId].filter(Boolean).join(' ') || undefined}
        onClick={handleClick}
        onKeyDown={handleKeyDown}
        onDragOver={handleDragOver}
        onDragEnter={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        className={cn(
          'flex flex-col items-center justify-center rounded-lg border-2 border-dashed px-6 py-8 text-center transition-colors',
          'cursor-pointer',
          isDragOver
            ? 'border-primary-500 bg-primary-50'
            : error
              ? 'border-danger-300 bg-danger-50/50'
              : 'border-secondary-300 bg-secondary-50/50 hover:border-secondary-400 hover:bg-secondary-50',
          isDisabled && 'cursor-not-allowed opacity-50',
        )}
      >
        {/* Upload icon */}
        <UploadCloud className="mb-3 h-10 w-10 text-secondary-400" aria-hidden="true" />
        <p className="text-sm font-medium text-secondary-700">
          {uploading ? 'Uploading...' : label}
        </p>
        {hint && !uploading && (
          <p id={hintId} className="mt-1 text-xs text-secondary-500">
            {hint}
          </p>
        )}
      </div>

      <input
        ref={inputRef}
        type="file"
        accept={accept}
        multiple={multiple}
        onChange={(e) => validateAndSelect(e.target.files)}
        className="hidden"
        tabIndex={-1}
        aria-hidden="true"
      />

      {/* Upload progress bar */}
      {uploading && uploadProgress != null && (
        <div className="mt-2">
          <div className="flex items-center justify-between text-xs text-secondary-500 mb-1">
            <span>Uploading...</span>
            <span>{Math.round(uploadProgress)}%</span>
          </div>
          <div className="h-2 w-full overflow-hidden rounded-full bg-secondary-200">
            <div
              className="h-full rounded-full bg-primary-500 transition-all duration-300"
              style={{ width: `${Math.min(100, Math.max(0, uploadProgress))}%` }}
            />
          </div>
        </div>
      )}

      {showFileList && selectedFiles.length > 0 && (
        <ul className="mt-2 space-y-1">
          {selectedFiles.map((file, i) => (
            <li key={i} className="flex items-center gap-2 text-sm text-secondary-600">
              <FileText className="h-4 w-4 shrink-0 text-secondary-400" aria-hidden="true" />
              <span className="truncate">{file.name}</span>
              <span className="shrink-0 text-xs text-secondary-400">
                ({(file.size / 1024).toFixed(0)} KB)
              </span>
              {!uploading && onRemoveFile && (
                <button
                  type="button"
                  onClick={(e) => { e.stopPropagation(); handleRemoveFile(i); }}
                  className="ml-auto shrink-0 rounded p-0.5 text-secondary-400 hover:bg-secondary-100 hover:text-danger-500"
                  aria-label={`Remove ${file.name}`}
                >
                  <X className="h-4 w-4" aria-hidden="true" />
                </button>
              )}
            </li>
          ))}
        </ul>
      )}

      {error && (
        <p id={errorId} className="mt-1 text-sm text-danger-600">
          {error}
        </p>
      )}
    </div>
  );
}
