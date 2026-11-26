import { render, screen, within } from '@testing-library/react';
import { vi } from 'vitest';
import type { ReleaseNotes, SourceConflict } from '@/api/types';
import { SourcesPanel } from './SourcesPanel';

const conflict = (chosen: string): SourceConflict => ({
  unit: 'GET /orders',
  field: 'limit',
  values: [
    // the same page stating two values
    { url: 'https://x.com/orders', value: 50 },
    { url: 'https://x.com/orders', value: 250 },
  ],
  chosen,
  reason: null,
});

describe('SourcesPanel with repeated conflicts', () => {
  it('shows every row when two have the same unit and field, with unique keys', () => {
    const errors = vi.spyOn(console, 'error').mockImplementation(() => undefined);
    try {
      render(<SourcesPanel n={{ conflicts: [conflict('50'), conflict('250')] } as ReleaseNotes} />);
      const list = screen.getByRole('list', { name: 'Source conflicts' });
      expect(list.querySelectorAll(':scope > li')).toHaveLength(2);
      expect(within(list).getAllByText('GET /orders')).toHaveLength(2);
      expect(within(list).getAllByRole('link')).toHaveLength(4);
      // React reports a repeated key on the console
      expect(errors.mock.calls.map((c) => String(c[0])).filter((m) => /same key/.test(m))).toEqual(
        [],
      );
    } finally {
      errors.mockRestore();
    }
  });
});
