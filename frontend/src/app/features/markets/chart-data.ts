import { decimalPlaces, toChartNumber } from '../../core/market-data/decimal';
import { CandleOut } from '../../core/market-data/market-data.models';
import { isValidTimeZone } from '../../core/time/local-time';

/** Framework-agnostic candle for drawing. `time` is seconds since the epoch (an instant, so
 * zone-free): the zone only matters when it is written on screen. */
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

/** The window of time on screen, seconds since the epoch. */
export interface TimeRange {
  from: number;
  to: number;
}

/** When the person was looking at the newest candle, the same-width window slides forward so
 * the candles that just arrived are in view; if they were looking at older history, it stays
 * exactly where it was. `previousLast`/`newLast` are the open times of the newest candle before
 * and after the update. */
export function followLatest(
  visible: TimeRange | null,
  previousLast: number | null,
  newLast: number | null,
): TimeRange | null {
  if (visible === null || previousLast === null || newLast === null) return visible;
  if (newLast <= previousLast || visible.to < previousLast) return visible;
  const shift = newLast - previousLast;
  return { from: visible.from + shift, to: visible.to + shift };
}

// lightweight-charts' TickMarkType values, restated so this file needs no chart library.
const TICK_YEAR = 0;
const TICK_MONTH = 1;
const TICK_DAY = 2;
const TICK_TIME = 3;
const TICK_TIME_WITH_SECONDS = 4;

/** Text of a time-axis tick, in the zone of the person: an hour for the intraday ticks, the day,
 * month or year where the axis changes. */
export function axisTickLabel(seconds: number, tickType: number, zone: string): string {
  const moment = new Date(seconds * 1000);
  switch (tickType) {
    case TICK_YEAR:
      return formatWith(zone, { year: 'numeric' }, moment);
    case TICK_MONTH:
      return formatWith(zone, { month: 'short' }, moment);
    case TICK_DAY:
      return formatWith(zone, { day: 'numeric' }, moment);
    case TICK_TIME_WITH_SECONDS:
      return formatWith(zone, { hour: '2-digit', minute: '2-digit', second: '2-digit' }, moment);
    case TICK_TIME:
    default:
      return formatWith(zone, { hour: '2-digit', minute: '2-digit' }, moment);
  }
}

/** Text under the crosshair: "25/09/2026 19:41", in the zone of the person. */
export function crosshairLabel(seconds: number, zone: string): string {
  return formatWith(
    zone,
    { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' },
    new Date(seconds * 1000),
  ).replace(',', '');
}

function formatWith(zone: string, options: Intl.DateTimeFormatOptions, moment: Date): string {
  return new Intl.DateTimeFormat('es-ES', {
    ...options,
    timeZone: isValidTimeZone(zone) ? zone : 'UTC',
    hourCycle: 'h23',
  }).format(moment);
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
