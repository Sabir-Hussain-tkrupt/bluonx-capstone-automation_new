import {
  cloneElement,
  isValidElement,
  useCallback,
  useEffect,
  useRef,
  useState,
} from 'react';
import type { ReactElement, ReactNode } from 'react';
import { cn } from '@/utils/cn';
import { DropdownMenuContext } from './context';

export interface DropdownMenuProps {
  /** Element that opens the menu. Rendered as-is (cloned to wire up click + a11y). */
  trigger: ReactNode;
  /** Horizontal edge the panel aligns to. Default `right`. */
  align?: 'left' | 'right';
  /** Whether the panel opens above or below the trigger. Default `bottom`. */
  side?: 'top' | 'bottom';
  /** Extra classes for the menu panel (e.g. a fixed width). */
  className?: string;
  /** `<DropdownMenuItem>`s (and optional non-interactive content). */
  children: ReactNode;
}

const positionClasses: Record<string, string> = {
  'bottom-right': 'right-0 top-full mt-2 origin-top-right',
  'bottom-left': 'left-0 top-full mt-2 origin-top-left',
  'top-right': 'right-0 bottom-full mb-2 origin-bottom-right',
  'top-left': 'left-0 bottom-full mb-2 origin-bottom-left',
};

export function DropdownMenu({
  trigger,
  align = 'right',
  side = 'bottom',
  className,
  children,
}: DropdownMenuProps) {
  const [isOpen, setIsOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);

  const close = useCallback(() => setIsOpen(false), []);

  const focusTrigger = useCallback(() => {
    (containerRef.current?.firstElementChild as HTMLElement | null)?.focus();
  }, []);

  // Close on outside click.
  useEffect(() => {
    if (!isOpen) return;
    function handleClickOutside(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setIsOpen(false);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [isOpen]);

  // Close on Escape and return focus to the trigger.
  useEffect(() => {
    if (!isOpen) return;
    function handleEscape(e: KeyboardEvent) {
      if (e.key === 'Escape') {
        setIsOpen(false);
        focusTrigger();
      }
    }
    document.addEventListener('keydown', handleEscape);
    return () => document.removeEventListener('keydown', handleEscape);
  }, [isOpen, focusTrigger]);

  // Focus the first enabled item when the menu opens.
  useEffect(() => {
    if (!isOpen) return;
    const first = menuRef.current?.querySelector<HTMLElement>(
      '[role="menuitem"]:not([disabled])',
    );
    first?.focus();
  }, [isOpen]);

  const handleMenuKeyDown = useCallback((e: React.KeyboardEvent) => {
    const items = Array.from(
      menuRef.current?.querySelectorAll<HTMLButtonElement>(
        '[role="menuitem"]:not([disabled])',
      ) ?? [],
    );
    if (items.length === 0) return;
    const currentIdx = items.indexOf(document.activeElement as HTMLButtonElement);

    if (e.key === 'ArrowDown') {
      e.preventDefault();
      const next = currentIdx < items.length - 1 ? currentIdx + 1 : 0;
      items[next]?.focus();
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      const prev = currentIdx > 0 ? currentIdx - 1 : items.length - 1;
      items[prev]?.focus();
    }
  }, []);

  const triggerEl = isValidElement(trigger)
    ? cloneElement(trigger as ReactElement<Record<string, unknown>>, {
        onClick: (e: React.MouseEvent) => {
          (trigger as ReactElement<{ onClick?: (e: React.MouseEvent) => void }>).props.onClick?.(e);
          setIsOpen((o) => !o);
        },
        'aria-haspopup': 'menu',
        'aria-expanded': isOpen,
      })
    : trigger;

  return (
    <div className="relative" ref={containerRef}>
      {triggerEl}
      {isOpen && (
        <DropdownMenuContext.Provider value={{ close }}>
          <div
            ref={menuRef}
            role="menu"
            onKeyDown={handleMenuKeyDown}
            className={cn(
              'absolute z-50 min-w-[12rem] rounded-lg border border-secondary-200 bg-white py-1 shadow-lg',
              positionClasses[`${side}-${align}`],
              className,
            )}
          >
            {children}
          </div>
        </DropdownMenuContext.Provider>
      )}
    </div>
  );
}
