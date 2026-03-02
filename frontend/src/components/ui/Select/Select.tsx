import { forwardRef, useId } from 'react';
import { cn } from '@/utils/cn';
import type { ComponentSize } from '../types';

export interface SelectOption {
  value: string;
  label: string;
  disabled?: boolean;
}

export interface SelectProps
  extends Omit<React.SelectHTMLAttributes<HTMLSelectElement>, 'size'> {
  options: SelectOption[];
  size?: ComponentSize;
  error?: string;
  placeholder?: string;
}

const sizeStyles: Record<ComponentSize, string> = {
  sm: 'h-8 text-sm',
  md: 'h-10 text-sm',
  lg: 'h-12 text-base',
};

export const Select = forwardRef<HTMLSelectElement, SelectProps>(
  ({ options, size = 'md', error, placeholder, className, id, ...rest }, ref) => {
    const autoId = useId();
    const selectId = id ?? autoId;
    const errorId = error ? `${selectId}-error` : undefined;

    return (
      <div className="w-full">
        <div className="relative">
          <select
            ref={ref}
            id={selectId}
            aria-invalid={error ? true : undefined}
            aria-describedby={errorId}
            className={cn(
              'w-full appearance-none rounded-lg border bg-white px-3 pr-10 transition-colors',
              'focus:border-primary-500 focus:ring-2 focus:ring-primary-500/20 focus:outline-none',
              error
                ? 'border-danger-500 focus:border-danger-500 focus:ring-danger-500/20'
                : 'border-secondary-300',
              sizeStyles[size],
              'disabled:cursor-not-allowed disabled:bg-secondary-50 disabled:opacity-50',
              className,
            )}
            {...rest}
          >
            {placeholder && (
              <option value="" disabled>
                {placeholder}
              </option>
            )}
            {options.map((option) => (
              <option key={option.value} value={option.value} disabled={option.disabled}>
                {option.label}
              </option>
            ))}
          </select>
          {/* Chevron icon */}
          <div className="pointer-events-none absolute inset-y-0 right-0 flex items-center pr-3">
            <svg
              className="h-4 w-4 text-secondary-400"
              viewBox="0 0 20 20"
              fill="currentColor"
              aria-hidden="true"
            >
              <path
                fillRule="evenodd"
                d="M5.23 7.21a.75.75 0 011.06.02L10 11.168l3.71-3.938a.75.75 0 111.08 1.04l-4.25 4.5a.75.75 0 01-1.08 0l-4.25-4.5a.75.75 0 01.02-1.06z"
                clipRule="evenodd"
              />
            </svg>
          </div>
        </div>
        {error && (
          <p id={errorId} className="mt-1 text-sm text-danger-600">
            {error}
          </p>
        )}
      </div>
    );
  },
);

Select.displayName = 'Select';
