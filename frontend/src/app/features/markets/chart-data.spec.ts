import { makeCandle } from '../../core/market-data/market-data.testing';
import { axisTickLabel, crosshairLabel, followLatest, formatAge, toChartData } from './chart-data';

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

// 2026-09-25 17:41:00 UTC is 19:41 in Madrid in summer (GMT+2), 12:41 in Bogota (GMT-5).
const INSTANT = Date.UTC(2026, 8, 25, 17, 41, 0) / 1000;

describe('axisTickLabel', () => {
  it('writes an intraday tick as the hour in the zone of the person', () => {
    expect(axisTickLabel(INSTANT, 3, 'Europe/Madrid')).toBe('19:41');
    expect(axisTickLabel(INSTANT, 3, 'America/Bogota')).toBe('12:41');
    expect(axisTickLabel(INSTANT, 3, 'UTC')).toBe('17:41');
  });

  it('writes the day, month and year ticks in that zone too', () => {
    // 23:30 UTC on the 24th is already the 25th in Madrid.
    const late = Date.UTC(2026, 8, 24, 23, 30, 0) / 1000;
    expect(axisTickLabel(late, 2, 'Europe/Madrid')).toBe('25');
    expect(axisTickLabel(late, 2, 'UTC')).toBe('24');
    expect(axisTickLabel(late, 0, 'UTC')).toBe('2026');
    expect(axisTickLabel(late, 1, 'UTC')).toMatch(/^sep/);
  });

  it('adds seconds for a seconds tick and falls back to UTC for an unknown zone', () => {
    expect(axisTickLabel(INSTANT + 5, 4, 'UTC')).toBe('17:41:05');
    expect(axisTickLabel(INSTANT, 3, 'Not/AZone')).toBe('17:41');
  });

  it('never shows 24:00 at midnight', () => {
    const midnight = Date.UTC(2026, 8, 25, 0, 0, 0) / 1000;
    expect(axisTickLabel(midnight, 3, 'UTC')).toBe('00:00');
  });
});

describe('crosshairLabel', () => {
  it('shows day and time in the zone of the person', () => {
    expect(crosshairLabel(INSTANT, 'Europe/Madrid')).toBe('25/09/2026 19:41');
    expect(crosshairLabel(INSTANT, 'America/Bogota')).toBe('25/09/2026 12:41');
  });

  it('follows a change of day', () => {
    const late = Date.UTC(2026, 8, 24, 23, 30, 0) / 1000;
    expect(crosshairLabel(late, 'Europe/Madrid')).toBe('25/09/2026 01:30');
  });
});

describe('followLatest', () => {
  const visible = { from: 1_000, to: 2_000 };

  it('slides the window forward when the person was looking at the newest candle', () => {
    expect(followLatest(visible, 2_000, 2_120)).toEqual({ from: 1_120, to: 2_120 });
    // Some blank space to the right of the last candle still counts as looking at it.
    expect(followLatest({ from: 1_000, to: 2_050 }, 2_000, 2_060)).toEqual({
      from: 1_060,
      to: 2_110,
    });
  });

  it('leaves the window alone when the person was looking at older history', () => {
    expect(followLatest(visible, 2_400, 2_520)).toEqual(visible);
  });

  it('leaves the window alone when nothing newer arrived', () => {
    expect(followLatest(visible, 2_000, 2_000)).toEqual(visible);
    expect(followLatest(visible, 2_000, 1_900)).toEqual(visible);
  });

  it('has nothing to follow on a first draw', () => {
    expect(followLatest(null, null, 2_000)).toBeNull();
    expect(followLatest(visible, null, 2_000)).toEqual(visible);
    expect(followLatest(visible, 2_000, null)).toEqual(visible);
  });
});
