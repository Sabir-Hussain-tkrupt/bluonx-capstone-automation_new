import { forwardRef } from 'react';
import { Loader2 } from 'lucide-react';
import { cn } from '@/utils/cn';
import type { ComponentSize, ComponentVariant } from '../types';

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ComponentVariant;
  size?: ComponentSize;
  isLoading?: boolean;
  leftIcon?: React.ReactNode;
  rightIcon?: React.ReactNode;
  fullWidth?: boolean;
}

const variantStyles: Record<ComponentVariant, string> = {
  primary: 'bg-primary-600 text-white hover:bg-primary-700 focus-visible:ring-primary-500',
  accent: 'bg-accent-600 text-white hover:bg-accent-700 focus-visible:ring-accent-500',
  secondary: 'bg-secondary-100 text-secondary-700 hover:bg-secondary-200 focus-visible:ring-secondary-500',
  danger: 'bg-danger-600 text-white hover:bg-danger-700 focus-visible:ring-danger-500',
  success: 'bg-success-600 text-white hover:bg-success-700 focus-visible:ring-success-500',
  warning: 'bg-warning-500 text-white hover:bg-warning-600 focus-visible:ring-warning-500',
  ghost: 'bg-transparent text-secondary-700 hover:bg-secondary-100 focus-visible:ring-secondary-500',
  outline: 'border border-secondary-300 bg-transparent text-secondary-700 hover:bg-secondary-50 focus-visible:ring-primary-500',
};

const sizeStyles: Record<ComponentSize, string> = {
  sm: 'px-3 py-1.5 text-sm gap-1.5',
  md: 'px-4 py-2 text-sm gap-2',
  lg: 'px-6 py-3 text-base gap-2',
};

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  (
    {
      variant = 'primary',
      size = 'md',
      isLoading = false,
      leftIcon,
      rightIcon,
      fullWidth = false,
      disabled,
      className,
      children,
      type = 'button',
      ...rest
    },
    ref,
  ) => {
    return (
      <button
        ref={ref}
        type={type}
        disabled={disabled || isLoading}
        aria-busy={isLoading || undefined}
        className={cn(
          'inline-flex cursor-pointer items-center justify-center rounded-lg font-medium transition-colors',
          'focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:outline-none',
          'disabled:pointer-events-none disabled:opacity-50',
          variantStyles[variant],
          sizeStyles[size],
          fullWidth && 'w-full',
          className,
        )}
        {...rest}
      >
        {isLoading && <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />}
        {!isLoading && leftIcon}
        {children}
        {!isLoading && rightIcon}
      </button>
    );
  },
);

Button.displayName = 'Button';
