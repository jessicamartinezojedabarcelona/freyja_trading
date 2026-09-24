import { marketLabel, productLabel } from './catalog-labels';

describe('catalog labels', () => {
  it('translates the codes the catalog has today', () => {
    expect(marketLabel({ code: 'CRYPTO', display_name: 'Crypto' })).toBe('Cripto');
    expect(marketLabel({ code: 'FOREX', display_name: 'Forex' })).toBe('Forex');
    expect(productLabel({ code: 'SPOT', display_name: 'Spot' })).toBe('Spot');
    expect(productLabel({ code: 'BINARY_OPTION', display_name: 'Binary option' })).toBe(
      'Opción binaria',
    );
  });

  it('keeps the catalog name for a code it does not know, instead of hiding it', () => {
    expect(marketLabel({ code: 'COMMODITIES', display_name: 'Commodities' })).toBe('Commodities');
    expect(productLabel({ code: 'FUTURE', display_name: 'Future' })).toBe('Future');
  });
});
