import { cn } from '@/utils/cn';
import type { ComponentSize } from '../types';

export interface CardProps {
  children: React.ReactNode;
  title?: string;
  subtitle?: string;
  actions?: React.ReactNode;
  padding?: ComponentSize;
  className?: string;
}

const paddingStyles: Record<ComponentSize, string> = {
  sm: 'p-4',
  md: 'p-6',
  lg: 'p-8',
};

export function Card({
  children,
  title,
  subtitle,
  actions,
  padding = 'md',
  className,
}: CardProps) {
  const hasHeader = title || subtitle || actions;

  return (
    <section
      aria-label={title}
      className={cn('rounded-lg border border-secondary-200 bg-white shadow-sm', className)}
    >
      {hasHeader && (
        <div className="flex items-start justify-between border-b border-secondary-200 px-6 py-4">
          <div>
            {title && (
              <h3 className="text-base font-semibold text-secondary-900">{title}</h3>
            )}
            {subtitle && (
              <p className="mt-0.5 text-sm text-secondary-500">{subtitle}</p>
            )}
          </div>
          {actions && <div className="ml-4 flex shrink-0 items-center gap-2">{actions}</div>}
        </div>
      )}
      <div className={paddingStyles[padding]}>{children}</div>
    </section>
  );
}
