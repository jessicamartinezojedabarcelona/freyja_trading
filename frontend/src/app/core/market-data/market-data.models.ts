// Typed mirror of the backend's stored-candles contract
// (GET /api/v1/market-data/candles, MARKET-DATA-PERSISTENCE-001, ADR 0003).
//
// Prices and volume arrive as exact decimal STRINGS ("84805.61"): never parse
// them into numbers for anything but drawing (see decimal.ts).

export type DataQuality = 'OK' | 'DEGRADED' | 'UNAVAILABLE';

export type FreshnessStatus = 'FRESH' | 'STALE' | 'NO_DATA';

// Every code the backend can emit, listed verbatim so a new one is a compile
// error in quality-labels.ts instead of an unexplained message on screen.
export type QualityIssueCode =
  | 'OPEN_CANDLE_EXCLUDED'
  | 'DUPLICATE_DROPPED'
  | 'OUT_OF_ORDER'
  | 'GAP'
  | 'INCOMPLETE_RANGE'
  | 'STALE'
  | 'INSTRUMENT_NOT_TRADING'
  | 'REVISED_CANDLE'
  | 'PROVIDER_FAILING'
  | 'RATE_LIMITED'
  | 'TIMEOUT'
  | 'PROVIDER_ERROR'
  | 'INVALID_RESPONSE'
  | 'SYMBOL_MISMATCH'
  | 'NO_DATA';

export interface CandleOut {
  /** Candle covers [open_time, close_time), ISO-8601 UTC. */
  open_time: string;
  close_time: string;
  open: string;
  high: string;
  low: string;
  close: string;
  volume: string;
  /** Quality of the batch the candle arrived in. */
  quality: DataQuality;
  /** When Freyja first received it. */
  received_at: string;
}

export interface QualityIssueOut {
  code: QualityIssueCode;
  /** Technical detail in English; never shown to the user as is. */
  detail: string;
}

export interface GapOut {
  after_open_time: string;
  missing: number;
}

export interface FreshnessOut {
  status: FreshnessStatus;
  checked_at: string;
  latest_open_time: string | null;
  latest_close_time: string | null;
  latest_received_at: string | null;
}

export interface ProviderStatusOut {
  last_attempt_at: string;
  last_success_at: string | null;
  last_status: DataQuality;
  last_issue_codes: string[];
  last_detail: string | null;
  consecutive_failures: number;
}

export interface CandleSeriesOut {
  instrument_id: string;
  data_source_code: string;
  timeframe_code: string;
  /** Oldest first. Empty does not mean "zero": read quality and issues. */
  candles: CandleOut[];
  quality: DataQuality;
  issues: QualityIssueOut[];
  gaps: GapOut[];
  freshness: FreshnessOut;
  provider: ProviderStatusOut | null;
  has_more: boolean;
  next_start: string | null;
}

export interface CandleQuery {
  instrumentId: string;
  dataSourceCode: string;
  /** Backend default is 1m when omitted. */
  timeframeCode?: string;
  /** ISO-8601 with a time zone. */
  start?: string;
  end?: string;
  limit?: number;
}
