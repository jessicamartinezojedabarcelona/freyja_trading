// Builders for tests only (never imported by application code). They produce
// values shaped exactly like the API's responses, so a spec states only what it
// cares about and the rest stays realistic.

import {
  DataSourceInstrumentOut,
  InstrumentMappingsOut,
  InstrumentOut,
  TimeframeRef,
} from '../catalog/catalog.models';
import { CandleOut, CandleSeriesOut } from './market-data.models';

export const INSTRUMENT_ID = '87b6b903-4029-51cb-ad54-ae000a760df7';
export const OTHER_INSTRUMENT_ID = '92dabb5e-0862-5dcd-a339-64a647368d37';

const BASE = Date.UTC(2026, 8, 24, 12, 0, 0);

export function isoAt(minutes: number): string {
  return new Date(BASE + minutes * 60_000).toISOString();
}

/** A 1-minute candle opening `minute` minutes after 12:00 UTC. */
export function makeCandle(minute: number, overrides: Partial<CandleOut> = {}): CandleOut {
  return {
    open_time: isoAt(minute),
    close_time: isoAt(minute + 1),
    open: '100.1',
    high: '102',
    low: '99',
    close: '101',
    volume: '10.5',
    quality: 'OK',
    received_at: isoAt(minute + 1),
    ...overrides,
  };
}

export function makeSeries(overrides: Partial<CandleSeriesOut> = {}): CandleSeriesOut {
  const candles = overrides.candles ?? [makeCandle(0), makeCandle(1), makeCandle(2)];
  const last = candles.at(-1);
  return {
    instrument_id: INSTRUMENT_ID,
    data_source_code: 'BINANCE',
    timeframe_code: '1m',
    candles,
    quality: 'OK',
    issues: [],
    gaps: [],
    freshness: {
      status: 'FRESH',
      checked_at: isoAt(4),
      latest_open_time: last?.open_time ?? null,
      latest_close_time: last?.close_time ?? null,
      latest_received_at: last?.received_at ?? null,
    },
    provider: {
      last_attempt_at: isoAt(4),
      last_success_at: isoAt(4),
      last_status: 'OK',
      last_issue_codes: [],
      last_detail: null,
      consecutive_failures: 0,
    },
    has_more: false,
    next_start: null,
    ...overrides,
  };
}

function timeframe(code: string, seconds: number): TimeframeRef {
  return { id: `tf-${code}`, code, display_name: code, duration_seconds: seconds };
}

export const CATALOG_TIMEFRAMES: TimeframeRef[] = [
  timeframe('1m', 60),
  timeframe('5m', 300),
  timeframe('15m', 900),
  timeframe('1h', 3600),
  timeframe('4h', 14400),
];

export function makeInstrument(overrides: Partial<InstrumentOut> = {}): InstrumentOut {
  return {
    instrument_id: INSTRUMENT_ID,
    market: { id: 'm-crypto', code: 'CRYPTO', display_name: 'Crypto' },
    product_type: { id: 'p-spot', code: 'SPOT', display_name: 'Spot' },
    canonical_symbol: 'BTC/USDT',
    base_asset: null,
    quote_asset: null,
    underlying_asset: null,
    underlying_instrument_id: null,
    is_active: true,
    timeframes: CATALOG_TIMEFRAMES,
    ...overrides,
  };
}

export function makeSourceMapping(
  code: string,
  name: string,
  overrides: Partial<DataSourceInstrumentOut> = {},
): DataSourceInstrumentOut {
  return {
    id: `map-${code}`,
    data_source: {
      id: `ds-${code}`,
      code,
      display_name: name,
      source_type: 'EXCHANGE',
      is_active: true,
    },
    provider_symbol: 'BTCUSDT',
    purpose: 'ANALYSIS',
    is_active: true,
    ...overrides,
  };
}

export function makeMappings(
  sources: DataSourceInstrumentOut[] = [makeSourceMapping('BINANCE', 'Binance')],
  instrumentId = INSTRUMENT_ID,
): InstrumentMappingsOut {
  return { instrument_id: instrumentId, venue_instruments: [], data_source_instruments: sources };
}
