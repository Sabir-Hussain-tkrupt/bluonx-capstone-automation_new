import { forwardRef, useId } from 'react';
import { cn } from '@/utils/cn';
import type { ComponentSize } from '../types';

export interface TextInputProps
  extends Omit<React.InputHTMLAttributes<HTMLInputElement>, 'size'> {
  size?: ComponentSize;
  error?: string | boolean;
  leftAddon?: React.ReactNode;
  rightAddon?: React.ReactNode;
}

const sizeStyles: Record<ComponentSize, string> = {
  sm: 'h-8 text-sm',
  md: 'h-10 text-sm',
  lg: 'h-12 text-base',
};

export const TextInput = forwardRef<HTMLInputElement, TextInputProps>(
  ({ size = 'md', error, leftAddon, rightAddon, className, id, ...rest }, ref) => {
    const autoId = useId();
    const inputId = id ?? autoId;
    const hasError = !!error;

    return (
      <div className="w-full">
        <div className="relative flex items-center">
          {leftAddon && (
            <div className="pointer-events-none absolute left-3 flex items-center text-secondary-400">
              {leftAddon}
            </div>
          )}
          <input
            ref={ref}
            id={inputId}
            aria-invalid={hasError ? true : undefined}
            className={cn(
              'w-full rounded-lg border bg-white px-3 transition-colors',
              'focus:border-primary-500 focus:ring-2 focus:ring-primary-500/20 focus:outline-none',
              'placeholder:text-secondary-400',
              hasError
                ? 'border-danger-500 focus:border-danger-500 focus:ring-danger-500/20'
                : 'border-secondary-300',
              sizeStyles[size],
              !!leftAddon && 'pl-10',
              !!rightAddon && 'pr-10',
              'disabled:cursor-not-allowed disabled:bg-secondary-50 disabled:opacity-50',
              className,
            )}
            {...rest}
          />
          {rightAddon && (
            <div className="absolute right-3 flex items-center text-secondary-400">
              {rightAddon}
            </div>
          )}
        </div>
      </div>
    );
  },
);

TextInput.displayName = 'TextInput';
