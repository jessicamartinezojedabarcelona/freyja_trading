import { CATALOG_TIMEFRAMES } from '../../core/market-data/market-data.testing';
import {
  DEFAULT_TIMEFRAME_CODE,
  PERIOD_GROUPS,
  REFERENCE_PERIODS,
  buildPeriodOptions,
  periodLabel,
  pickTimeframe,
} from './periods';

describe('periods', () => {
  it('uses 1 minute as the standard period', () => {
    expect(DEFAULT_TIMEFRAME_CODE).toBe('1m');
  });

  it('lists the full reference set, ordered, with the labels brokers use', () => {
    expect(REFERENCE_PERIODS.map((p) => p.label)).toEqual([
      '5seg',
      '10seg',
      '15seg',
      '20seg',
      '30seg',
      '1m',
      '2m',
      '5m',
      '10m',
      '15m',
      '30m',
      '1hs',
      '4hs',
      '1d',
      '7d',
      '1M',
    ]);
    const seconds = REFERENCE_PERIODS.map((p) => p.seconds);
    expect(seconds).toEqual([...seconds].sort((a, b) => a - b));
  });

  describe('buildPeriodOptions', () => {
    it('keeps every reference period visible and enables only what the catalog enables', () => {
      const options = buildPeriodOptions(CATALOG_TIMEFRAMES);

      expect(options).toHaveLength(REFERENCE_PERIODS.length);
      const enabled = options.filter((o) => o.available).map((o) => o.code);
      expect(enabled).toEqual(['1m', '5m', '15m', '1h', '4h']);
      expect(options.find((o) => o.code === '30s')?.available).toBe(false);
      expect(options.find((o) => o.code === '1M')?.available).toBe(false);
    });

    it('shows nothing as available when the instrument has no period', () => {
      expect(buildPeriodOptions([]).every((o) => !o.available)).toBe(true);
    });

    it('adds a catalog period the reference list does not know, in the right group', () => {
      const odd = { id: 'x', code: '45s', display_name: '45 seconds', duration_seconds: 45 };
      const options = buildPeriodOptions([...CATALOG_TIMEFRAMES, odd]);

      const added = options.find((o) => o.code === '45s');
      expect(added).toMatchObject({ available: true, group: 'Segundos', label: '45s' });
      const seconds = options.map((o) => o.seconds);
      expect(seconds).toEqual([...seconds].sort((a, b) => a - b));
    });

    it('places every option in one of the known groups', () => {
      for (const option of buildPeriodOptions(CATALOG_TIMEFRAMES)) {
        expect(PERIOD_GROUPS).toContain(option.group);
      }
    });
  });

  describe('pickTimeframe', () => {
    it('honours the requested period when the catalog enables it', () => {
      expect(pickTimeframe('5m', CATALOG_TIMEFRAMES)).toBe('5m');
    });

    it('falls back to 1m when the request is missing or not enabled', () => {
      expect(pickTimeframe(null, CATALOG_TIMEFRAMES)).toBe('1m');
      expect(pickTimeframe('30s', CATALOG_TIMEFRAMES)).toBe('1m');
      expect(pickTimeframe('nonsense', CATALOG_TIMEFRAMES)).toBe('1m');
    });

    it('prefers 1m over a shorter period that is also enabled', () => {
      const withSeconds = [
        { id: 'tf-30s', code: '30s', display_name: '30 seconds', duration_seconds: 30 },
        ...CATALOG_TIMEFRAMES,
      ];
      expect(pickTimeframe(null, withSeconds)).toBe('1m');
      expect(pickTimeframe('30s', withSeconds)).toBe('30s'); // unless asked for explicitly
    });

    it('falls back to the shortest enabled period when 1m is not enabled', () => {
      const withoutOneMinute = CATALOG_TIMEFRAMES.filter((t) => t.code !== '1m');
      expect(pickTimeframe(null, withoutOneMinute)).toBe('5m');
    });

    it('returns null when the instrument has no period at all', () => {
      expect(pickTimeframe('1m', [])).toBeNull();
    });
  });

  describe('periodLabel', () => {
    it('shows the broker label and leaves unknown codes as they are', () => {
      expect(periodLabel('1h')).toBe('1hs');
      expect(periodLabel('30s')).toBe('30seg');
      expect(periodLabel('45s')).toBe('45s');
    });
  });
});
