import { forwardRef } from 'react';
import type { ReactNode } from 'react';
import { cn } from '@/utils/cn';

export interface IconButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  /** The icon to render (e.g. a lucide icon). */
  icon: ReactNode;
  /** Required for accessibility — icon-only buttons have no text label. */
  'aria-label': string;
  size?: 'sm' | 'md' | 'lg';
  variant?: 'ghost' | 'outline';
}

const sizeStyles: Record<NonNullable<IconButtonProps['size']>, string> = {
  sm: 'h-8 w-8',
  md: 'h-9 w-9',
  lg: 'h-10 w-10',
};

const variantStyles: Record<NonNullable<IconButtonProps['variant']>, string> = {
  ghost: 'bg-transparent text-secondary-600 hover:bg-secondary-100 hover:text-secondary-900',
  outline:
    'border border-secondary-200 bg-white text-secondary-600 hover:bg-secondary-50',
};

export const IconButton = forwardRef<HTMLButtonElement, IconButtonProps>(
  ({ icon, size = 'md', variant = 'ghost', disabled, className, type = 'button', ...rest }, ref) => {
    return (
      <button
        ref={ref}
        type={type}
        disabled={disabled}
        className={cn(
          'inline-flex cursor-pointer items-center justify-center rounded-md transition-colors',
          'focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 focus-visible:outline-none',
          'disabled:pointer-events-none disabled:opacity-50',
          sizeStyles[size],
          variantStyles[variant],
          className,
        )}
        {...rest}
      >
        {icon}
      </button>
    );
  },
);

IconButton.displayName = 'IconButton';
