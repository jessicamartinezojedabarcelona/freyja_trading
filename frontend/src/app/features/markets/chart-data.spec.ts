import { isoAt, makeCandle } from '../../core/market-data/market-data.testing';
import { formatAge, formatUtc, toChartData } from './chart-data';

describe('toChartData', () => {
  it('converts strings to numbers and the open time to UTC seconds', () => {
    const { candles } = toChartData([makeCandle(0, { open: '84805.61', volume: '44.20358' })]);

    expect(candles).toEqual([
      {
        time: Date.UTC(2026, 8, 24, 12, 0, 0) / 1000,
        open: 84805.61,
        high: 102,
        low: 99,
        close: 101,
        volume: 44.20358,
      },
    ]);
  });

  it('sorts by time and keeps one candle per instant (the last one wins)', () => {
    const { candles } = toChartData([
      makeCandle(2),
      makeCandle(0),
      makeCandle(1, { close: '50' }),
      makeCandle(1, { close: '60' }),
    ]);

    expect(candles.map((c) => c.time)).toEqual(
      [0, 1, 2].map((m) => Date.UTC(2026, 8, 24, 12, m) / 1000),
    );
    expect(candles[1].close).toBe(60);
  });

  it('takes the price precision from the exact strings, capped at 8', () => {
    expect(toChartData([makeCandle(0)]).precision).toBe(1);
    expect(
      toChartData([makeCandle(0, { open: '0.5' }), makeCandle(1, { low: '0.512' })]).precision,
    ).toBe(3);
    expect(toChartData([makeCandle(0, { open: '0.123456789012' })]).precision).toBe(8);
    expect(
      toChartData([makeCandle(0, { open: '100', high: '100', low: '100', close: '100' })])
        .precision,
    ).toBe(0);
  });

  it('skips a candle whose time cannot be read instead of drawing it at a wrong place', () => {
    const { candles } = toChartData([makeCandle(0, { open_time: 'not-a-date' }), makeCandle(1)]);
    expect(candles).toHaveLength(1);
  });

  it('returns nothing for nothing', () => {
    expect(toChartData([])).toEqual({ candles: [], precision: 0 });
  });

  it('refuses a price it cannot represent rather than drawing NaN', () => {
    expect(() => toChartData([makeCandle(0, { close: 'oops' })])).toThrow();
  });
});

describe('formatAge', () => {
  it('uses the two most useful units and drops zeros', () => {
    expect(formatAge(0)).toBe('0 s');
    expect(formatAge(45)).toBe('45 s');
    expect(formatAge(60)).toBe('1 min');
    expect(formatAge(94)).toBe('1 min 34 s');
    expect(formatAge(3600)).toBe('1 h');
    expect(formatAge(3660)).toBe('1 h 1 min');
    expect(formatAge(7500)).toBe('2 h 5 min');
    expect(formatAge(90_000)).toBe('1 d 1 h');
    expect(formatAge(86_400)).toBe('1 d');
  });

  it('never goes negative when clocks disagree slightly', () => {
    expect(formatAge(-3)).toBe('0 s');
  });
});

describe('formatUtc', () => {
  it('always states the zone', () => {
    expect(formatUtc(isoAt(7.5))).toMatch(/24\/09\/2026.*12:07:30 UTC$/);
  });

  it('shows a dash for a missing or unreadable instant', () => {
    expect(formatUtc(null)).toBe('—');
    expect(formatUtc('garbage')).toBe('—');
  });

  it('does not depend on the browser time zone', () => {
    // 23:30 UTC stays 23:30 UTC even where the local date is already the next day.
    expect(formatUtc('2026-09-24T23:30:00Z')).toMatch(/24\/09\/2026.*23:30:00 UTC$/);
  });
});
