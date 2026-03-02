import { useCallback, useId, useRef, useState } from 'react';
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
}: FileUploadProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [isDragOver, setIsDragOver] = useState(false);
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const componentId = useId();
  const errorId = error ? `${componentId}-error` : undefined;
  const hintId = hint ? `${componentId}-hint` : undefined;

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

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    if (!disabled) setIsDragOver(true);
  };

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(false);
    if (!disabled) validateAndSelect(e.dataTransfer.files);
  };

  const handleClick = () => {
    if (!disabled) inputRef.current?.click();
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if ((e.key === 'Enter' || e.key === ' ') && !disabled) {
      e.preventDefault();
      inputRef.current?.click();
    }
  };

  return (
    <div className="w-full">
      <div
        role="button"
        tabIndex={disabled ? -1 : 0}
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
          disabled && 'cursor-not-allowed opacity-50',
        )}
      >
        {/* Upload icon */}
        <svg
          className="mb-3 h-10 w-10 text-secondary-400"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.5"
          aria-hidden="true"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M12 16.5V9.75m0 0l3 3m-3-3l-3 3M6.75 19.5a4.5 4.5 0 01-1.41-8.775 5.25 5.25 0 0110.338-2.32 3.75 3.75 0 013.572 5.595H6.75z"
          />
        </svg>
        <p className="text-sm font-medium text-secondary-700">{label}</p>
        {hint && (
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

      {selectedFiles.length > 0 && (
        <ul className="mt-2 space-y-1">
          {selectedFiles.map((file, i) => (
            <li key={i} className="flex items-center gap-2 text-sm text-secondary-600">
              <svg
                className="h-4 w-4 shrink-0 text-secondary-400"
                viewBox="0 0 20 20"
                fill="currentColor"
                aria-hidden="true"
              >
                <path d="M3 3.5A1.5 1.5 0 014.5 2h6.879a1.5 1.5 0 011.06.44l3.122 3.12A1.5 1.5 0 0116 6.622V16.5a1.5 1.5 0 01-1.5 1.5h-11A1.5 1.5 0 012 16.5v-13z" />
              </svg>
              <span className="truncate">{file.name}</span>
              <span className="shrink-0 text-xs text-secondary-400">
                ({(file.size / 1024).toFixed(0)} KB)
              </span>
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
