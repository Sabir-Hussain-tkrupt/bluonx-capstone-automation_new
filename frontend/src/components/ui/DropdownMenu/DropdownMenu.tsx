import {
  cloneElement,
  isValidElement,
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
} from 'react';
import { createPortal } from 'react-dom';
import type { ReactElement, ReactNode } from 'react';
import { cn } from '@/utils/cn';
import { DropdownMenuContext } from './context';

export interface DropdownMenuProps {
  /** Element that opens the menu. Rendered as-is (cloned to wire up click + a11y). */
  trigger: ReactNode;
  /** Horizontal edge the panel aligns to. Default `right`. */
  align?: 'left' | 'right';
  /**
   * Preferred vertical placement. Default `bottom`. The menu flips to the other
   * side on its own when the preferred one would run off the viewport, so
   * callers only need this to express a preference, not to avoid clipping.
   */
  side?: 'top' | 'bottom';
  /** Extra classes for the menu panel (e.g. a fixed width). */
  className?: string;
  /** `<DropdownMenuItem>`s (and optional non-interactive content). */
  children: ReactNode;
}

/** Distance between the trigger and the panel. */
const GAP = 8;
/** Minimum breathing room between the panel and the viewport edge. */
const VIEWPORT_MARGIN = 8;

interface MenuPosition {
  top: number;
  left: number;
  /** Placement actually used, after collision handling. */
  side: 'top' | 'bottom';
}

const originClasses: Record<string, string> = {
  'bottom-right': 'origin-top-right',
  'bottom-left': 'origin-top-left',
  'top-right': 'origin-bottom-right',
  'top-left': 'origin-bottom-left',
};

function clamp(value: number, min: number, max: number) {
  return Math.min(Math.max(value, min), Math.max(min, max));
}

/**
 * Trigger + popup menu.
 *
 * The panel is portaled to `document.body` and positioned `fixed` from the
 * trigger's viewport rect. That is deliberate: an absolutely-positioned panel is
 * clipped by any `overflow` ancestor, and the most common host is a table row
 * (the shared `Table` clips on both its card wrapper and its scroll wrapper), so
 * a row menu would be cut off at the table's edge. Positioning against the
 * viewport instead means the only constraint is the screen, which the flip below
 * handles.
 */
export function DropdownMenu({
  trigger,
  align = 'right',
  side = 'bottom',
  className,
  children,
}: DropdownMenuProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [position, setPosition] = useState<MenuPosition | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);

  const close = useCallback(() => setIsOpen(false), []);

  const focusTrigger = useCallback(() => {
    (containerRef.current?.firstElementChild as HTMLElement | null)?.focus();
  }, []);

  const updatePosition = useCallback(() => {
    const container = containerRef.current;
    const menu = menuRef.current;
    if (!container || !menu) return;

    // The container wraps the trigger, so its rect is the anchor. Using it (not
    // the trigger element) keeps alignment identical to the old `right-0`.
    const anchor = container.getBoundingClientRect();
    const { width, height } = menu.getBoundingClientRect();
    const viewportH = window.innerHeight;
    const viewportW = window.innerWidth;

    // Honour `side` when the panel fits there; otherwise flip, but only if the
    // other side actually has room (no room either way keeps the preference).
    const fitsBelow = anchor.bottom + GAP + height <= viewportH - VIEWPORT_MARGIN;
    const fitsAbove = anchor.top - GAP - height >= VIEWPORT_MARGIN;
    const resolvedSide: 'top' | 'bottom' =
      side === 'bottom'
        ? fitsBelow || !fitsAbove
          ? 'bottom'
          : 'top'
        : fitsAbove || !fitsBelow
          ? 'top'
          : 'bottom';

    const top =
      resolvedSide === 'bottom' ? anchor.bottom + GAP : anchor.top - GAP - height;
    const left = align === 'right' ? anchor.right - width : anchor.left;

    setPosition({
      top: clamp(top, VIEWPORT_MARGIN, viewportH - height - VIEWPORT_MARGIN),
      left: clamp(left, VIEWPORT_MARGIN, viewportW - width - VIEWPORT_MARGIN),
      side: resolvedSide,
    });
  }, [align, side]);

  // Measure before paint so the panel never shows at a stale position.
  useLayoutEffect(() => {
    if (!isOpen) return;
    updatePosition();
  }, [isOpen, updatePosition]);

  // Follow the trigger while the page (or any scroll container under it) moves.
  useEffect(() => {
    if (!isOpen) return;
    const reposition = () => updatePosition();
    window.addEventListener('scroll', reposition, true);
    window.addEventListener('resize', reposition);
    return () => {
      window.removeEventListener('scroll', reposition, true);
      window.removeEventListener('resize', reposition);
    };
  }, [isOpen, updatePosition]);

  // Close on outside click. The panel is portaled, so it is not a descendant of
  // the container — it has to be tested separately or a mousedown on an item
  // would close the menu before its click handler ever runs.
  useEffect(() => {
    if (!isOpen) return;
    function handleClickOutside(e: MouseEvent) {
      const target = e.target as Node;
      if (containerRef.current?.contains(target)) return;
      if (menuRef.current?.contains(target)) return;
      setIsOpen(false);
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
          // Drop the previous measurement on the event that opens the menu
          // rather than in an effect. The panel renders hidden until
          // `position` is set, so clearing it here is what stops a reopen from
          // painting at the last trigger's coordinates. Unconditional is safe:
          // `position` is never read while the menu is closed.
          setPosition(null);
          setIsOpen((o) => !o);
        },
        'aria-haspopup': 'menu',
        'aria-expanded': isOpen,
      })
    : trigger;

  return (
    <div className="relative" ref={containerRef}>
      {triggerEl}
      {isOpen &&
        createPortal(
          <DropdownMenuContext.Provider value={{ close }}>
            <div
              ref={menuRef}
              role="menu"
              onKeyDown={handleMenuKeyDown}
              style={{
                top: position?.top ?? 0,
                left: position?.left ?? 0,
                // Hidden for the measuring pass only; useLayoutEffect resolves
                // the position before the browser paints.
                visibility: position ? 'visible' : 'hidden',
              }}
              className={cn(
                'fixed z-50 min-w-[12rem] rounded-lg border border-secondary-200 bg-white py-1 shadow-lg',
                originClasses[`${position?.side ?? side}-${align}`],
                className,
              )}
            >
              {children}
            </div>
          </DropdownMenuContext.Provider>,
          document.body,
        )}
    </div>
  );
}
