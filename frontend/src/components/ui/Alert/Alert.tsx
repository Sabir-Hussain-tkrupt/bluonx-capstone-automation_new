import { AlertTriangle, CheckCircle2, Info, X, XCircle } from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import { cn } from '@/utils/cn';
import type { StatusVariant } from '../types';

export interface AlertProps {
  variant: StatusVariant;
  title?: string;
  children: React.ReactNode;
  dismissible?: boolean;
  onDismiss?: () => void;
  icon?: React.ReactNode;
  className?: string;
}

const variantStyles: Record<StatusVariant, string> = {
  success: 'bg-success-50 border-success-500 text-success-700',
  danger: 'bg-danger-50 border-danger-500 text-danger-700',
  warning: 'bg-warning-50 border-warning-500 text-warning-700',
  info: 'bg-info-50 border-info-500 text-info-700',
  neutral: 'bg-secondary-50 border-secondary-300 text-secondary-700',
};

const iconByVariant: Record<StatusVariant, LucideIcon> = {
  success: CheckCircle2,
  danger: XCircle,
  warning: AlertTriangle,
  info: Info,
  neutral: Info,
};

function DefaultIcon({ variant }: { variant: StatusVariant }) {
  const Icon = iconByVariant[variant];
  return <Icon className="h-5 w-5 shrink-0" aria-hidden="true" />;
}

export function Alert({
  variant,
  title,
  children,
  dismissible = false,
  onDismiss,
  icon,
  className,
}: AlertProps) {
  return (
    <div
      role="alert"
      className={cn(
        'flex gap-3 rounded-lg border-l-4 p-4',
        variantStyles[variant],
        className,
      )}
    >
      {icon ?? <DefaultIcon variant={variant} />}
      <div className="flex-1">
        {title && <p className="font-medium">{title}</p>}
        <div className={cn(title && 'mt-1', 'text-sm')}>{children}</div>
      </div>
      {dismissible && (
        <button
          type="button"
          onClick={onDismiss}
          className="shrink-0 rounded-lg p-0.5 opacity-70 hover:opacity-100 focus-visible:ring-2 focus-visible:ring-current focus-visible:outline-none"
          aria-label="Dismiss"
        >
          <X className="h-4 w-4" aria-hidden="true" />
        </button>
      )}
    </div>
  );
}
