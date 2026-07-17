import { cn } from '@/utils/cn';

export interface StarRatingProps {
  /** Current rating 1-5, or null when unset. */
  value: number | null;
  /** Called with the new 1-5 value on click / keyboard select. Omit in readOnly mode. */
  onChange?: (value: number) => void;
  /** Render as static stars with no interaction (display of an existing rating). */
  readOnly?: boolean;
  size?: 'sm' | 'md' | 'lg';
  /** Accessible label for the group. */
  label?: string;
  className?: string;
}

const MAX = 5;

const sizeStyles = {
  sm: 'h-4 w-4',
  md: 'h-6 w-6',
  lg: 'h-8 w-8',
} as const;

function StarIcon({ filled, className }: { filled: boolean; className?: string }) {
  return (
    <svg
      viewBox="0 0 20 20"
      aria-hidden="true"
      className={className}
      fill={filled ? 'currentColor' : 'none'}
      stroke="currentColor"
      strokeWidth={filled ? 0 : 1.5}
    >
      <path d="M9.049 2.927c.3-.921 1.603-.921 1.902 0l1.286 3.958a1 1 0 00.95.69h4.162c.969 0 1.371 1.24.588 1.81l-3.367 2.446a1 1 0 00-.364 1.118l1.287 3.957c.3.922-.755 1.688-1.54 1.118l-3.366-2.446a1 1 0 00-1.176 0l-3.366 2.446c-.784.57-1.838-.196-1.539-1.118l1.287-3.957a1 1 0 00-.364-1.118L2.05 9.385c-.783-.57-.38-1.81.588-1.81h4.163a1 1 0 00.95-.69l1.286-3.958z" />
    </svg>
  );
}

/**
 * 1-5 star rating input. Controlled: pass `value` (null = unset) and `onChange`.
 * Keyboard-accessible as a radiogroup — arrow keys move the selection, number
 * keys 1-5 set it directly. `readOnly` renders static stars with no inputs.
 */
export function StarRating({
  value,
  onChange,
  readOnly = false,
  size = 'md',
  label = 'Rating',
  className,
}: StarRatingProps) {
  const stars = Array.from({ length: MAX }, (_, i) => i + 1);

  if (readOnly) {
    return (
      <div
        className={cn('inline-flex items-center gap-1', className)}
        role="img"
        aria-label={value ? `${value} out of ${MAX} stars` : 'Not rated'}
      >
        {stars.map((star) => (
          <StarIcon
            key={star}
            filled={value != null && star <= value}
            className={cn(sizeStyles[size], value != null && star <= value ? 'text-warning-500' : 'text-secondary-300')}
          />
        ))}
      </div>
    );
  }

  const move = (next: number) => {
    const clamped = Math.min(MAX, Math.max(1, next));
    onChange?.(clamped);
  };

  const handleKeyDown = (e: React.KeyboardEvent, star: number) => {
    if (e.key === 'ArrowRight' || e.key === 'ArrowUp') {
      e.preventDefault();
      move((value ?? 0) + 1);
    } else if (e.key === 'ArrowLeft' || e.key === 'ArrowDown') {
      e.preventDefault();
      move((value ?? MAX + 1) - 1);
    } else if (e.key >= '1' && e.key <= '5') {
      e.preventDefault();
      move(Number(e.key));
    } else if (e.key === ' ' || e.key === 'Enter') {
      e.preventDefault();
      move(star);
    }
  };

  return (
    <div
      className={cn('inline-flex items-center gap-1', className)}
      role="radiogroup"
      aria-label={label}
    >
      {stars.map((star) => {
        const active = value != null && star <= value;
        return (
          <button
            key={star}
            type="button"
            role="radio"
            aria-checked={value === star}
            aria-label={`${star} star${star > 1 ? 's' : ''}`}
            // Only the selected star (or the first when unset) is in the tab order,
            // so the group is a single tab stop; arrows move within it.
            tabIndex={value === star || (value == null && star === 1) ? 0 : -1}
            onClick={() => move(star)}
            onKeyDown={(e) => handleKeyDown(e, star)}
            className={cn(
              'cursor-pointer rounded transition-colors focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:outline-none',
              active ? 'text-warning-500' : 'text-secondary-300 hover:text-warning-400',
            )}
          >
            <StarIcon filled={active} className={sizeStyles[size]} />
          </button>
        );
      })}
    </div>
  );
}
