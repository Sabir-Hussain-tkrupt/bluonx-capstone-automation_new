import { useId } from 'react';
import { cn } from '@/utils/cn';
import type { ComponentSize } from '../types';

export interface RadioOption {
  value: string;
  label: string;
  description?: string;
  disabled?: boolean;
}

export interface RadioGroupProps {
  name: string;
  options: RadioOption[];
  value?: string;
  onChange?: (value: string) => void;
  orientation?: 'horizontal' | 'vertical';
  size?: ComponentSize;
  error?: string;
  disabled?: boolean;
  legend?: string;
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

export function RadioGroup({
  name,
  options,
  value,
  onChange,
  orientation = 'vertical',
  size = 'md',
  error,
  disabled = false,
  legend,
}: RadioGroupProps) {
  const groupId = useId();
  const errorId = error ? `${groupId}-error` : undefined;

  return (
    <fieldset disabled={disabled} aria-describedby={errorId}>
      {legend && (
        <legend className="mb-2 text-sm font-medium text-secondary-900">{legend}</legend>
      )}
      <div
        className={cn(
          'flex',
          orientation === 'vertical' ? 'flex-col gap-2' : 'flex-row flex-wrap gap-4',
        )}
      >
        {options.map((option) => {
          const optionId = `${groupId}-${option.value}`;
          return (
            <label
              key={option.value}
              htmlFor={optionId}
              className={cn(
                'flex items-start gap-3 cursor-pointer',
                option.disabled && 'cursor-not-allowed opacity-50',
              )}
            >
              <input
                id={optionId}
                type="radio"
                name={name}
                value={option.value}
                disabled={option.disabled}
                onChange={() => onChange?.(option.value)}
                {...(value !== undefined ? { checked: value === option.value } : {})}
                className={cn(
                  'mt-0.5 shrink-0 border-secondary-300 accent-primary-600',
                  'focus:ring-2 focus:ring-primary-500/20 focus:ring-offset-2',
                  sizeStyles[size],
                )}
              />
              <div>
                <span className={cn('font-medium text-secondary-900', labelSizeStyles[size])}>
                  {option.label}
                </span>
                {option.description && (
                  <p className="mt-0.5 text-sm text-secondary-500">{option.description}</p>
                )}
              </div>
            </label>
          );
        })}
      </div>
      {error && (
        <p id={errorId} className="mt-1 text-sm text-danger-600">
          {error}
        </p>
      )}
    </fieldset>
  );
}
