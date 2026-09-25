import { CandleOut } from '../../core/market-data/market-data.models';

/** Joins the candles already on screen with a fresh page, one per open time, oldest first.
 * The fresh page wins where they overlap; candles it does not cover (older pages the person
 * loaded) are kept, so a refresh never throws history away. */
export function mergeCandles(
  current: readonly CandleOut[],
  fresh: readonly CandleOut[],
): CandleOut[] {
  const byTime = new Map<number, CandleOut>();
  for (const candle of [...current, ...fresh]) {
    const time = Date.parse(candle.open_time);
    if (!Number.isNaN(time)) byTime.set(time, candle);
  }
  return [...byTime.entries()].sort(([a], [b]) => a - b).map(([, candle]) => candle);
}
