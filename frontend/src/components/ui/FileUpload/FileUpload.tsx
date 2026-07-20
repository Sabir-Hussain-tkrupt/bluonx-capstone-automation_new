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
    [maxSizeMB, onFilesSelected, onError],
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

      {selectedFiles.length > 0 && (
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
