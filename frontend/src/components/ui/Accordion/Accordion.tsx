import { useCallback, useState } from 'react';
import { cn } from '@/utils/cn';

export interface AccordionItem {
  id: string;
  title: string;
  content: React.ReactNode;
  disabled?: boolean;
}

export interface AccordionProps {
  items: AccordionItem[];
  allowMultiple?: boolean;
  defaultOpen?: string[];
  className?: string;
}

export function Accordion({
  items,
  allowMultiple = false,
  defaultOpen = [],
  className,
}: AccordionProps) {
  const [openItems, setOpenItems] = useState<Set<string>>(new Set(defaultOpen));

  const toggle = useCallback(
    (id: string) => {
      setOpenItems((prev) => {
        const next = new Set(prev);
        if (next.has(id)) {
          next.delete(id);
        } else {
          if (!allowMultiple) next.clear();
          next.add(id);
        }
        return next;
      });
    },
    [allowMultiple],
  );

  return (
    <div className={cn('divide-y divide-secondary-200 rounded-lg border border-secondary-200', className)}>
      {items.map((item) => {
        const isOpen = openItems.has(item.id);
        const contentId = `accordion-content-${item.id}`;
        const triggerId = `accordion-trigger-${item.id}`;

        return (
          <div key={item.id}>
            <button
              type="button"
              id={triggerId}
              aria-expanded={isOpen}
              aria-controls={contentId}
              disabled={item.disabled}
              onClick={() => toggle(item.id)}
              className={cn(
                'flex w-full items-center justify-between px-4 py-3 text-left text-sm font-medium text-secondary-900 transition-colors',
                'hover:bg-secondary-50 focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-primary-500 focus-visible:outline-none',
                item.disabled && 'cursor-not-allowed opacity-50',
              )}
            >
              {item.title}
              <svg
                className={cn(
                  'h-4 w-4 shrink-0 text-secondary-500 transition-transform duration-200',
                  isOpen && 'rotate-180',
                )}
                viewBox="0 0 20 20"
                fill="currentColor"
                aria-hidden="true"
              >
                <path
                  fillRule="evenodd"
                  d="M5.23 7.21a.75.75 0 011.06.02L10 11.168l3.71-3.938a.75.75 0 111.08 1.04l-4.25 4.5a.75.75 0 01-1.08 0l-4.25-4.5a.75.75 0 01.02-1.06z"
                  clipRule="evenodd"
                />
              </svg>
            </button>
            <div
              id={contentId}
              role="region"
              aria-labelledby={triggerId}
              className={cn(
                'overflow-hidden transition-all duration-200',
                isOpen ? 'max-h-[2000px] opacity-100' : 'max-h-0 opacity-0',
              )}
            >
              <div className="px-4 pb-4 pt-1 text-sm text-secondary-600">{item.content}</div>
            </div>
          </div>
        );
      })}
    </div>
  );
}
