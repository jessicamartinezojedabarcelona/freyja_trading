import { makeCandle } from '../../core/market-data/market-data.testing';
import { mergeCandles } from './merge-candles';

const opens = (candles: { open_time: string }[]) => candles.map((c) => c.open_time);

describe('mergeCandles', () => {
  it('adds the candles that are new, oldest first', () => {
    const merged = mergeCandles([makeCandle(0), makeCandle(1)], [makeCandle(1), makeCandle(2)]);
    expect(opens(merged)).toEqual(opens([makeCandle(0), makeCandle(1), makeCandle(2)]));
  });

  it('keeps older pages the fresh page does not cover', () => {
    const older = [makeCandle(0), makeCandle(1), makeCandle(2)];
    const fresh = [makeCandle(100), makeCandle(101)];
    expect(mergeCandles([...older, makeCandle(99)], fresh)).toHaveLength(6);
  });

  it('lets the fresh candle win where they overlap, one per open time', () => {
    const merged = mergeCandles([makeCandle(5, { close: '1' })], [makeCandle(5, { close: '2' })]);
    expect(merged).toHaveLength(1);
    expect(merged[0].close).toBe('2');
  });

  it('sorts by time, not by the order they arrive in', () => {
    const merged = mergeCandles([makeCandle(9)], [makeCandle(3), makeCandle(6)]);
    expect(opens(merged)).toEqual(opens([makeCandle(3), makeCandle(6), makeCandle(9)]));
  });

  it('ignores a candle whose time cannot be read, never inventing one', () => {
    const broken = { ...makeCandle(1), open_time: 'garbage' };
    expect(mergeCandles([makeCandle(0)], [broken])).toHaveLength(1);
  });

  it('does not change what it was given', () => {
    const current = [makeCandle(0)];
    mergeCandles(current, [makeCandle(1)]);
    expect(current).toHaveLength(1);
  });
});
