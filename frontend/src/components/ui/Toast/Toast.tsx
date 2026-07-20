import { useEffect } from 'react';
import { AlertTriangle, CheckCircle2, Info, X, XCircle } from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import { cn } from '@/utils/cn';
import type { StatusVariant } from '../types';

export interface ToastData {
  id: string;
  variant: StatusVariant;
  title?: string;
  message: string;
  duration?: number;
}

interface ToastProps {
  toast: ToastData;
  onDismiss: (id: string) => void;
}

const variantStyles: Record<StatusVariant, string> = {
  success: 'border-success-500 bg-success-50 text-success-700',
  danger: 'border-danger-500 bg-danger-50 text-danger-700',
  warning: 'border-warning-500 bg-warning-50 text-warning-700',
  info: 'border-info-500 bg-info-50 text-info-700',
  neutral: 'border-secondary-300 bg-white text-secondary-700',
};

const iconByVariant: Record<StatusVariant, LucideIcon> = {
  success: CheckCircle2,
  danger: XCircle,
  warning: AlertTriangle,
  info: Info,
  neutral: Info,
};

export function Toast({ toast: t, onDismiss }: ToastProps) {
  const duration = t.duration ?? 5000;
  const Icon = iconByVariant[t.variant];

  useEffect(() => {
    if (duration <= 0) return;
    const timer = setTimeout(() => onDismiss(t.id), duration);
    return () => clearTimeout(timer);
  }, [t.id, duration, onDismiss]);

  return (
    <div
      role="alert"
      className={cn(
        'pointer-events-auto flex w-80 items-start gap-3 rounded-lg border-l-4 p-4 shadow-lg',
        'animate-[slideIn_0.2s_ease-out]',
        variantStyles[t.variant],
      )}
    >
      <Icon className="h-5 w-5 shrink-0" aria-hidden="true" />
      <div className="flex-1 min-w-0">
        {t.title && <p className="font-medium">{t.title}</p>}
        <p className={cn('text-sm', t.title && 'mt-0.5')}>{t.message}</p>
      </div>
      <button
        type="button"
        onClick={() => onDismiss(t.id)}
        className="shrink-0 rounded-lg p-0.5 opacity-70 hover:opacity-100 focus-visible:ring-2 focus-visible:ring-current focus-visible:outline-none"
        aria-label="Dismiss notification"
      >
        <X className="h-4 w-4" aria-hidden="true" />
      </button>
    </div>
  );
}
