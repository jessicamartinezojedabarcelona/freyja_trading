import { decimalPlaces, toChartNumber } from '../../core/market-data/decimal';
import { CandleOut } from '../../core/market-data/market-data.models';

/** Framework-agnostic candle for drawing. `time` is seconds since the epoch, UTC. */
export interface ChartCandle {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface ChartData {
  candles: ChartCandle[];
  /** Fractional digits to show, taken from the exact strings (capped at 8). */
  precision: number;
}

const MAX_PRECISION = 8;

/** Converts API candles for drawing: sorted by time, one per instant. This is
 * the only place decimal strings become numbers, and only for the chart. */
export function toChartData(candles: readonly CandleOut[]): ChartData {
  const byTime = new Map<number, ChartCandle>();
  let precision = 0;
  for (const candle of candles) {
    const time = Math.floor(Date.parse(candle.open_time) / 1000);
    if (Number.isNaN(time)) continue;
    byTime.set(time, {
      time,
      open: toChartNumber(candle.open),
      high: toChartNumber(candle.high),
      low: toChartNumber(candle.low),
      close: toChartNumber(candle.close),
      volume: toChartNumber(candle.volume),
    });
    for (const value of [candle.open, candle.high, candle.low, candle.close]) {
      precision = Math.max(precision, decimalPlaces(value));
    }
  }
  return {
    candles: [...byTime.values()].sort((a, b) => a.time - b.time),
    precision: Math.min(precision, MAX_PRECISION),
  };
}

const UTC_FORMAT = new Intl.DateTimeFormat('es-ES', {
  timeZone: 'UTC',
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
  second: '2-digit',
  hour12: false,
});

/** "24/09/2026, 12:07:30 UTC" for an ISO instant; the zone is always explicit. */
export function formatUtc(iso: string | null): string {
  if (iso === null) return '—';
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return '—';
  return `${UTC_FORMAT.format(date)} UTC`;
}

/** "1 min 34 s", "2 h 5 min", "1 d 3 h": a duration in the two most useful units. */
export function formatAge(totalSeconds: number): string {
  const seconds = Math.max(0, Math.floor(totalSeconds));
  const days = Math.floor(seconds / 86_400);
  const hours = Math.floor((seconds % 86_400) / 3_600);
  const minutes = Math.floor((seconds % 3_600) / 60);
  const rest = seconds % 60;
  const parts: [number, string][] =
    days > 0
      ? [
          [days, 'd'],
          [hours, 'h'],
        ]
      : hours > 0
        ? [
            [hours, 'h'],
            [minutes, 'min'],
          ]
        : minutes > 0
          ? [
              [minutes, 'min'],
              [rest, 's'],
            ]
          : [[rest, 's']];
  const shown = parts.filter(([value]) => value > 0);
  return shown.length === 0 ? '0 s' : shown.map(([value, unit]) => `${value} ${unit}`).join(' ');
}
