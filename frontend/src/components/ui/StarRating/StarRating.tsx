import { Star } from 'lucide-react';
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
    <Star
      aria-hidden="true"
      className={className}
      fill={filled ? 'currentColor' : 'none'}
    />
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
