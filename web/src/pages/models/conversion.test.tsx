import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderApp } from '@/test/render';
import { ConversionChip, ConversionDetail, conversionLabel, mapEntries } from './Conversion';

describe('conversion labels', () => {
  it('says each kind in words and leaves an unknown kind as written', () => {
    expect(conversionLabel('money-minor')).toBe('money in minor units');
    expect(conversionLabel('enum')).toBe('enum map');
    expect(conversionLabel('brand-new-kind')).toBe('brand-new-kind');
  });
  it('reads a map as text pairs and drops what is not a value', () => {
    expect(
      mapEntries({ kind: 'enum', map: { a: 'x', b: 2 as unknown as string, c: {} as never } }),
    ).toEqual([
      ['a', 'x'],
      ['b', '2'],
    ]);
  });
});

describe('code-system conversions', () => {
  it('say "code system" and show the systems from the format, with nothing else to open', async () => {
    expect(conversionLabel('code-system')).toBe('code system');
    render(
      <ConversionChip
        conversion={{ kind: 'code-system', format: 'ISO 3166-1 alpha-3 -> alpha-2' }}
      />,
    );
    await userEvent.click(screen.getByText('code system'));
    expect(screen.getByText('systems:').parentElement).toHaveTextContent(
      'systems: ISO 3166-1 alpha-3 -> alpha-2',
    );
    expect(screen.queryByRole('list')).not.toBeInTheDocument();
  });
});

describe('ConversionChip', () => {
  it('shows nothing without a conversion', () => {
    expect(render(<ConversionChip conversion={undefined} />).container).toBeEmptyDOMElement();
    expect(render(<ConversionChip conversion={null} />).container).toBeEmptyDOMElement();
  });

  it('is a plain chip, nothing to open, when the kind is all there is', () => {
    const { container } = render(<ConversionChip conversion={{ kind: 'id-type' }} />);
    expect(screen.getByText('id type')).toBeInTheDocument();
    expect(container.querySelector('details')).toBeNull();
  });

  it('opens to the enum map, the format and the note, as plain text', async () => {
    render(
      <ConversionChip
        conversion={{
          kind: 'enum',
          map: { yes: 'true', no: 'false' },
          format: 'lowercase',
          note: '<b>not html</b>',
        }}
      />,
    );
    const summary = screen.getByText('enum map').closest('summary') as HTMLElement;
    await userEvent.click(summary);
    const list = screen.getByRole('list', { name: 'enum map: API value to canonical value' });
    expect(within(list).getAllByRole('listitem')).toHaveLength(2);
    expect(within(list).getByText('yes').closest('li')).toHaveTextContent('yes → true');
    expect(screen.getByText('lowercase')).toBeInTheDocument();
    expect(screen.getByText('<b>not html</b>')).toBeInTheDocument();
  });

  it('calls the format of a meta entry its key', () => {
    render(<ConversionDetail conversion={{ kind: 'meta-entry', format: '_tracking_number' }} />);
    expect(screen.getByText('key:')).toBeInTheDocument();
    expect(screen.getByText('_tracking_number')).toBeInTheDocument();
  });
});

describe('on the model page', () => {
  it('shows a chip per mapped API field in the table, opening to the map', async () => {
    renderApp('/models/snap_8f3a21');
    await userEvent.click(await screen.findByRole('radio', { name: 'Table' }));
    const row = (await screen.findByRole('rowheader', { name: /^allow_backorder/ })).closest(
      'tr',
    ) as HTMLElement;
    const [shopify, woo, mirakl] = Array.from(row.querySelectorAll(':scope > td'));
    expect(within(shopify as HTMLElement).getByText('enum map')).toBeInTheDocument();
    await userEvent.click(within(woo as HTMLElement).getByText('enum map'));
    expect(
      within(woo as HTMLElement)
        .getByText('notify')
        .closest('li'),
    ).toHaveTextContent('notify → true');
    // an API that states no conversion shows none
    expect(within(mirakl as HTMLElement).queryByText('enum map')).not.toBeInTheDocument();
  });

  it('shows the conversion in the mapping detail of the selected field', async () => {
    renderApp('/models/snap_8f3a21?field=allow_backorder&api=shopify');
    const detail = await screen.findByRole('region', { name: 'Mapping detail' });
    expect(await within(detail).findByText('Conversion')).toBeInTheDocument();
    expect(within(detail).getByText('enum map')).toBeInTheDocument();
    expect(within(detail).getByText('deny').closest('li')).toHaveTextContent('deny → false');
    expect(
      within(detail).getByText('Shopify names the policy; the canonical field is a flag.'),
    ).toBeInTheDocument();
  });
});
