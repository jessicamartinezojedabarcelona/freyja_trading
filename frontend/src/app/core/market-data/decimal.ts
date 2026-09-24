// Exact decimal helpers for the strings the API sends.
//
// Money-like values never go through `number` for anything that is compared or
// decided: `compareDecimals` works on the digits. `toChartNumber` exists only
// for the drawing boundary (the chart library takes numbers) and its result
// must never be used to compute or decide anything.

const DECIMAL = /^(-)?(\d+)(?:\.(\d+))?$/;

interface Parsed {
  negative: boolean;
  /** All digits, no separator. */
  digits: bigint;
  /** How many of those digits are fractional. */
  scale: number;
}

function parse(value: string): Parsed {
  const match = DECIMAL.exec(value);
  if (match === null) {
    throw new Error(`Not a plain decimal: ${JSON.stringify(value)}`);
  }
  const [, sign, whole = '0', fraction = ''] = match;
  const digits = BigInt(`${whole}${fraction}`);
  return { negative: sign === '-' && digits !== 0n, digits, scale: fraction.length };
}

/** Exact three-way comparison of two plain decimal strings. */
export function compareDecimals(a: string, b: string): -1 | 0 | 1 {
  const left = parse(a);
  const right = parse(b);
  const scale = Math.max(left.scale, right.scale);
  const l = left.digits * 10n ** BigInt(scale - left.scale) * (left.negative ? -1n : 1n);
  const r = right.digits * 10n ** BigInt(scale - right.scale) * (right.negative ? -1n : 1n);
  return l === r ? 0 : l < r ? -1 : 1;
}

/** Number of fractional digits in a plain decimal string ("0.00012" → 5). */
export function decimalPlaces(value: string): number {
  return parse(value).scale;
}

/** DRAWING ONLY. Converts to the binary float the chart library requires. */
export function toChartNumber(value: string): number {
  parse(value); // reject anything that is not a plain decimal instead of drawing NaN
  return Number(value);
}
