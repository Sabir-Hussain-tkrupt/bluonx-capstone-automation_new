import { Inbox } from 'lucide-react';
import { cn } from '@/utils/cn';

export interface EmptyStateProps {
  icon?: React.ReactNode;
  title: string;
  description?: string;
  action?: React.ReactNode;
  className?: string;
}

function DefaultIcon() {
  return <Inbox className="h-12 w-12 text-secondary-300" aria-hidden="true" />;
}

export function EmptyState({
  icon,
  title,
  description,
  action,
  className,
}: EmptyStateProps) {
  return (
    <div
      className={cn(
        'flex flex-col items-center justify-center py-12 text-center',
        className,
      )}
    >
      <div className="mb-4">{icon ?? <DefaultIcon />}</div>
      <h3 className="text-lg font-medium text-secondary-900">{title}</h3>
      {description && (
        <p className="mt-1 max-w-sm text-sm text-secondary-500">{description}</p>
      )}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}
