import { compareDecimals, decimalPlaces, toChartNumber } from './decimal';

describe('compareDecimals', () => {
  it('orders plain decimals exactly', () => {
    expect(compareDecimals('84833.11', '84805.61')).toBe(1);
    expect(compareDecimals('84805.61', '84833.11')).toBe(-1);
    expect(compareDecimals('0.5', '0.5')).toBe(0);
  });

  it('treats trailing zeros and a missing fraction as the same value', () => {
    expect(compareDecimals('1.5', '1.50000000')).toBe(0);
    expect(compareDecimals('100', '100.0')).toBe(0);
    expect(compareDecimals('2', '1.999999999')).toBe(1);
  });

  it('is exact where a binary float is not', () => {
    // Both round to the same number when parsed as floats.
    expect(Number('9007199254740993')).toBe(Number('9007199254740992'));
    expect(compareDecimals('9007199254740993', '9007199254740992')).toBe(1);
    expect(compareDecimals('0.30000000000000004', '0.3')).toBe(1);
    expect(compareDecimals('0.1', '0.10000000000000001')).toBe(-1);
  });

  it('handles negatives and treats -0 as 0', () => {
    expect(compareDecimals('-1.5', '-1.4')).toBe(-1);
    expect(compareDecimals('-0.1', '0.1')).toBe(-1);
    expect(compareDecimals('-0', '0')).toBe(0);
  });

  it('rejects anything that is not a plain decimal', () => {
    for (const bad of ['', 'abc', '1e5', '1,5', '.5', '5.', ' 1', 'NaN', 'Infinity']) {
      expect(() => compareDecimals(bad, '1'), bad).toThrow();
    }
  });
});

describe('decimalPlaces', () => {
  it('counts fractional digits', () => {
    expect(decimalPlaces('100')).toBe(0);
    expect(decimalPlaces('84805.61')).toBe(2);
    expect(decimalPlaces('0.00012340')).toBe(8);
  });
});

describe('toChartNumber', () => {
  it('converts for drawing', () => {
    expect(toChartNumber('84805.61')).toBe(84805.61);
    expect(toChartNumber('0.5')).toBe(0.5);
  });

  it('refuses values it cannot draw instead of returning NaN', () => {
    expect(() => toChartNumber('n/a')).toThrow();
  });
});
