import type { ComponentProps } from 'react';
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { Field } from '../Field';

const EM_DASH = '—';

/** Field is designed to sit inside a <dl>; render it the way the pages do. */
function renderField(props: ComponentProps<typeof Field>) {
  return render(
    <dl>
      <Field {...props} />
    </dl>,
  );
}

/** The row container is the div wrapping the dt/dd pair. */
function rowFor(labelText: string): HTMLElement {
  return screen.getByText(labelText).parentElement!;
}

describe('Field', () => {
  // The layout mechanism IS the unit under test here: the pair has to stay
  // bounded no matter how wide its container gets, so these assert on classes.
  // jsdom runs with css:false, so there is no computed layout to check instead.
  describe('layout', () => {
    it('lays the pair out as a two-column grid at sm and up', () => {
      renderField({ label: 'City', value: 'Austin' });
      const row = rowFor('City');

      expect(row.className).toContain('grid');
      expect(row.className).toContain('sm:grid-cols-[minmax(0,10rem)_minmax(0,1fr)]');
    });

    it('does not distribute the pair with justify-between', () => {
      renderField({ label: 'City', value: 'Austin' });

      expect(rowFor('City').className).not.toContain('justify-between');
    });

    it('does not right-align the value', () => {
      renderField({ label: 'City', value: 'Austin' });

      expect(screen.getByText('Austin').className).not.toContain('text-right');
    });

    it('does not lock the label to its intrinsic width', () => {
      renderField({ label: 'Insurance Expiration', value: 'Mar 14, 2026' });

      expect(screen.getByText('Insurance Expiration').className).not.toContain('shrink-0');
    });

    it('merges a passthrough className', () => {
      renderField({ label: 'City', value: 'Austin', className: 'pt-0' });

      expect(rowFor('City').className).toContain('pt-0');
    });
  });

  describe('semantics', () => {
    // The four detail pages wrap these rows in a <dl> and hang
    // `divide-y` off it, so the dt/dd pairing is load-bearing, not decorative.
    it('renders the label as a dt and the value as a dd', () => {
      renderField({ label: 'City', value: 'Austin' });

      expect(screen.getByText('City').tagName).toBe('DT');
      expect(screen.getByText('Austin').tagName).toBe('DD');
    });
  });

  describe('value fallback', () => {
    it.each([
      ['null', null],
      ['undefined', undefined],
      ['an empty string', ''],
    ])('renders the em dash when the value is %s', (_label, value) => {
      renderField({ label: 'Notes', value });

      expect(screen.getByText(EM_DASH)).toBeInTheDocument();
    });

    it('renders a ReactNode value intact', () => {
      renderField({
        label: 'Status',
        value: <span data-testid="badge">Approved</span>,
      });

      expect(screen.getByTestId('badge')).toHaveTextContent('Approved');
      expect(screen.queryByText(EM_DASH)).not.toBeInTheDocument();
    });
  });
});
