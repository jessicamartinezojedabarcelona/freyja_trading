import { TimeframeRef } from '../../core/catalog/catalog.models';

/** The candle period is chosen by the person using Freyja; 1 minute is the
 * standard when nothing else is asked for. */
export const DEFAULT_TIMEFRAME_CODE = '1m';

export type PeriodGroup = 'Segundos' | 'Minutos' | 'Horas' | 'Días y más';

export interface PeriodOption {
  code: string;
  label: string;
  seconds: number;
  group: PeriodGroup;
  /** True when the catalog enables this period for the selected instrument. */
  available: boolean;
}

interface ReferencePeriod {
  code: string;
  label: string;
  seconds: number;
  group: PeriodGroup;
}

// The full set of periods Freyja is meant to offer, as brokers show them. Only
// the ones the catalog enables are selectable today; the rest stay visible (and
// disabled, with the reason) instead of silently missing.
export const REFERENCE_PERIODS: readonly ReferencePeriod[] = [
  { code: '5s', label: '5seg', seconds: 5, group: 'Segundos' },
  { code: '10s', label: '10seg', seconds: 10, group: 'Segundos' },
  { code: '15s', label: '15seg', seconds: 15, group: 'Segundos' },
  { code: '20s', label: '20seg', seconds: 20, group: 'Segundos' },
  { code: '30s', label: '30seg', seconds: 30, group: 'Segundos' },
  { code: '1m', label: '1m', seconds: 60, group: 'Minutos' },
  { code: '2m', label: '2m', seconds: 120, group: 'Minutos' },
  { code: '5m', label: '5m', seconds: 300, group: 'Minutos' },
  { code: '10m', label: '10m', seconds: 600, group: 'Minutos' },
  { code: '15m', label: '15m', seconds: 900, group: 'Minutos' },
  { code: '30m', label: '30m', seconds: 1800, group: 'Minutos' },
  { code: '1h', label: '1hs', seconds: 3600, group: 'Horas' },
  { code: '4h', label: '4hs', seconds: 14400, group: 'Horas' },
  { code: '1d', label: '1d', seconds: 86400, group: 'Días y más' },
  { code: '7d', label: '7d', seconds: 604800, group: 'Días y más' },
  { code: '1M', label: '1M', seconds: 2592000, group: 'Días y más' },
];

export const PERIOD_GROUPS: readonly PeriodGroup[] = ['Segundos', 'Minutos', 'Horas', 'Días y más'];

function groupFor(seconds: number): PeriodGroup {
  if (seconds < 60) return 'Segundos';
  if (seconds < 3600) return 'Minutos';
  if (seconds < 86400) return 'Horas';
  return 'Días y más';
}

/** Human label of a period code; unknown codes are shown as they are. */
export function periodLabel(code: string): string {
  return REFERENCE_PERIODS.find((period) => period.code === code)?.label ?? code;
}

/** Reference periods plus any catalog period the reference list does not know,
 * ordered by duration, each flagged by whether the catalog enables it. */
export function buildPeriodOptions(enabled: readonly TimeframeRef[]): PeriodOption[] {
  const enabledCodes = new Set(enabled.map((timeframe) => timeframe.code));
  const options: PeriodOption[] = REFERENCE_PERIODS.map((period) => ({
    ...period,
    available: enabledCodes.has(period.code),
  }));
  const known = new Set(REFERENCE_PERIODS.map((period) => period.code));
  for (const timeframe of enabled) {
    if (!known.has(timeframe.code)) {
      options.push({
        code: timeframe.code,
        label: timeframe.code,
        seconds: timeframe.duration_seconds,
        group: groupFor(timeframe.duration_seconds),
        available: true,
      });
    }
  }
  return options.sort((a, b) => a.seconds - b.seconds);
}

/** The period to show: the requested one if the catalog enables it, otherwise
 * 1m, otherwise the shortest enabled one; null when the instrument has none. */
export function pickTimeframe(
  requested: string | null,
  enabled: readonly TimeframeRef[],
): string | null {
  const codes = new Set(enabled.map((timeframe) => timeframe.code));
  if (requested !== null && codes.has(requested)) return requested;
  if (codes.has(DEFAULT_TIMEFRAME_CODE)) return DEFAULT_TIMEFRAME_CODE;
  const shortest = [...enabled].sort((a, b) => a.duration_seconds - b.duration_seconds)[0];
  return shortest?.code ?? null;
}
