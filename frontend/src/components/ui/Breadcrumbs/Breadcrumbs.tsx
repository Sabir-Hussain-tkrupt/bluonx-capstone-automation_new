import { Link } from 'react-router-dom';
import { ChevronRight } from 'lucide-react';
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
  return <ChevronRight className="h-4 w-4 shrink-0 text-secondary-400" aria-hidden="true" />;
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
          // Entity crumbs carry real names, which can be long. Cap each one so
          // a single verbose project name shrinks in place rather than pushing
          // the whole trail wide; the full text stays available on hover.
          const labelClass = 'block max-w-[16ch] truncate text-sm sm:max-w-[24ch]';
          return (
            <li
              key={item.href ?? item.label}
              className="flex shrink-0 items-center gap-1.5 whitespace-nowrap"
            >
              {idx > 0 && (
                <span aria-hidden="true">
                  {separator ?? <DefaultSeparator />}
                </span>
              )}
              {isLast || !item.href ? (
                <span
                  className={cn(
                    labelClass,
                    isLast
                      ? 'font-medium text-secondary-900'
                      : 'text-secondary-500',
                  )}
                  aria-current={isLast ? 'page' : undefined}
                  title={item.label}
                >
                  {item.label}
                </span>
              ) : (
                <Link
                  to={item.href}
                  className={cn(labelClass, 'text-secondary-500 hover:text-secondary-700')}
                  title={item.label}
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
