import { forwardRef, useId } from 'react';
import { cn } from '@/utils/cn';
import type { ComponentSize } from '../types';

export interface DatePickerProps
  extends Omit<React.InputHTMLAttributes<HTMLInputElement>, 'type' | 'size'> {
  size?: ComponentSize;
  error?: string;
  minDate?: string;
  maxDate?: string;
}

const sizeStyles: Record<ComponentSize, string> = {
  sm: 'h-8 text-sm',
  md: 'h-10 text-sm',
  lg: 'h-12 text-base',
};

export const DatePicker = forwardRef<HTMLInputElement, DatePickerProps>(
  ({ size = 'md', error, minDate, maxDate, className, id, ...rest }, ref) => {
    const autoId = useId();
    const inputId = id ?? autoId;
    const errorId = error ? `${inputId}-error` : undefined;

    return (
      <div className="w-full">
        <input
          ref={ref}
          id={inputId}
          type="date"
          min={minDate}
          max={maxDate}
          aria-invalid={error ? true : undefined}
          aria-describedby={errorId}
          className={cn(
            'w-full rounded-lg border bg-white px-3 transition-colors',
            'focus:border-primary-500 focus:ring-2 focus:ring-primary-500/20 focus:outline-none',
            error
              ? 'border-danger-500 focus:border-danger-500 focus:ring-danger-500/20'
              : 'border-secondary-300',
            sizeStyles[size],
            'disabled:cursor-not-allowed disabled:bg-secondary-50 disabled:opacity-50',
            className,
          )}
          {...rest}
        />
        {error && (
          <p id={errorId} className="mt-1 text-sm text-danger-600">
            {error}
          </p>
        )}
      </div>
    );
  },
);

DatePicker.displayName = 'DatePicker';
