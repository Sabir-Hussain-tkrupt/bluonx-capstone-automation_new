import { forwardRef, useId } from 'react';
import { cn } from '@/utils/cn';
import type { ComponentSize } from '../types';

export interface CheckboxProps
  extends Omit<React.InputHTMLAttributes<HTMLInputElement>, 'type' | 'size'> {
  label: string;
  size?: ComponentSize;
  error?: string;
  description?: string;
}

const sizeStyles: Record<ComponentSize, string> = {
  sm: 'h-4 w-4',
  md: 'h-5 w-5',
  lg: 'h-6 w-6',
};

const labelSizeStyles: Record<ComponentSize, string> = {
  sm: 'text-sm',
  md: 'text-sm',
  lg: 'text-base',
};

export const Checkbox = forwardRef<HTMLInputElement, CheckboxProps>(
  ({ label, size = 'md', error, description, className, id, ...rest }, ref) => {
    const autoId = useId();
    const inputId = id ?? autoId;
    const errorId = error ? `${inputId}-error` : undefined;
    const descId = description ? `${inputId}-desc` : undefined;

    return (
      <div className="w-full">
        <label htmlFor={inputId} className="flex min-h-[44px] items-center gap-3 py-1 cursor-pointer">
          <input
            ref={ref}
            id={inputId}
            type="checkbox"
            aria-invalid={error ? true : undefined}
            aria-describedby={
              [errorId, descId].filter(Boolean).join(' ') || undefined
            }
            className={cn(
              'shrink-0 rounded border-secondary-300 accent-primary-600',
              'focus:ring-2 focus:ring-primary-500/20 focus:ring-offset-2',
              sizeStyles[size],
              'disabled:cursor-not-allowed disabled:opacity-50',
              className,
            )}
            {...rest}
          />
          <div>
            <span className={cn('font-medium text-secondary-900', labelSizeStyles[size])}>
              {label}
            </span>
            {description && (
              <p id={descId} className="mt-0.5 text-sm text-secondary-500">
                {description}
              </p>
            )}
          </div>
        </label>
        {error && (
          <p id={errorId} className="mt-1 ml-8 text-sm text-danger-600">
            {error}
          </p>
        )}
      </div>
    );
  },
);

Checkbox.displayName = 'Checkbox';
