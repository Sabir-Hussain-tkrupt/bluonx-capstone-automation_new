import { Link } from 'react-router-dom';
import { cn } from '@/utils/cn';

export interface BreadcrumbItem {
  label: string;
  href?: string;
}

export interface BreadcrumbsProps {
  items: BreadcrumbItem[];
  separator?: React.ReactNode;
  className?: string;
}

function DefaultSeparator() {
  return (
    <svg
      className="h-4 w-4 shrink-0 text-secondary-400"
      viewBox="0 0 20 20"
      fill="currentColor"
      aria-hidden="true"
    >
      <path
        fillRule="evenodd"
        d="M7.21 14.77a.75.75 0 01.02-1.06L11.168 10 7.23 6.29a.75.75 0 111.04-1.08l4.5 4.25a.75.75 0 010 1.08l-4.5 4.25a.75.75 0 01-1.06-.02z"
        clipRule="evenodd"
      />
    </svg>
  );
}

export function Breadcrumbs({
  items,
  separator,
  className,
}: BreadcrumbsProps) {
  if (items.length === 0) return null;

  return (
    <nav aria-label="Breadcrumb" className={className}>
      <ol className="flex items-center gap-1.5 overflow-x-auto scrollbar-hide">
        {items.map((item, idx) => {
          const isLast = idx === items.length - 1;
          return (
            <li key={idx} className="flex shrink-0 items-center gap-1.5 whitespace-nowrap">
              {idx > 0 && (
                <span aria-hidden="true">
                  {separator ?? <DefaultSeparator />}
                </span>
              )}
              {isLast || !item.href ? (
                <span
                  className={cn(
                    'text-sm',
                    isLast
                      ? 'font-medium text-secondary-900'
                      : 'text-secondary-500',
                  )}
                  aria-current={isLast ? 'page' : undefined}
                >
                  {item.label}
                </span>
              ) : (
                <Link
                  to={item.href}
                  className="text-sm text-secondary-500 hover:text-secondary-700"
                >
                  {item.label}
                </Link>
              )}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
