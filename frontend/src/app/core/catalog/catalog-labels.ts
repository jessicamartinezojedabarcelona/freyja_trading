// Spanish wording for catalog codes. The catalog stores English display names;
// what the person reads is decided here, and an unknown code keeps the catalog's
// own name instead of hiding it.

const MARKETS: Record<string, string> = {
  CRYPTO: 'Cripto',
  FOREX: 'Forex',
};

const PRODUCTS: Record<string, string> = {
  SPOT: 'Spot',
  BINARY_OPTION: 'Opción binaria',
};

interface Coded {
  code: string;
  display_name: string;
}

export function marketLabel(market: Coded): string {
  return MARKETS[market.code] ?? market.display_name;
}

export function productLabel(product: Coded): string {
  return PRODUCTS[product.code] ?? product.display_name;
}
