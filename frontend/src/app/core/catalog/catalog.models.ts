// Typed mirror of the backend's read-only catalog contract (POINT1-API-001).
// Every status union lists all of its backend values verbatim — never
// collapsed into a boolean, never reinterpreted client-side.

export interface Page<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

export interface MarketRef {
  id: string;
  code: string;
  display_name: string;
}

export interface ProductTypeRef {
  id: string;
  code: string;
  display_name: string;
}

export interface AssetRef {
  id: string;
  code: string;
  display_name: string;
}

export interface TimeframeRef {
  id: string;
  code: string;
  display_name: string;
  duration_seconds: number;
}

export interface InstrumentOut {
  instrument_id: string;
  market: MarketRef;
  product_type: ProductTypeRef;
  canonical_symbol: string;
  base_asset: AssetRef | null;
  quote_asset: AssetRef | null;
  underlying_asset: AssetRef | null;
  underlying_instrument_id: string | null;
  is_active: boolean;
  timeframes: TimeframeRef[];
}

export type VenueType = 'EXCHANGE' | 'BROKER';
export type DataSourceType = 'EXCHANGE' | 'BROKER' | 'MARKET_DATA';
export type DataSourceInstrumentPurpose = 'ANALYSIS' | 'SETTLEMENT';

export interface VenueOut {
  id: string;
  code: string;
  display_name: string;
  venue_type: VenueType;
  is_active: boolean;
}

export interface DataSourceOut {
  id: string;
  code: string;
  display_name: string;
  source_type: DataSourceType;
  is_active: boolean;
}

export interface VenueInstrumentOut {
  id: string;
  venue: VenueOut;
  provider_symbol: string;
  provider_contract_id: string | null;
  is_active: boolean;
}

export interface DataSourceInstrumentOut {
  id: string;
  data_source: DataSourceOut;
  provider_symbol: string;
  purpose: DataSourceInstrumentPurpose;
  is_active: boolean;
}

export interface InstrumentMappingsOut {
  instrument_id: string;
  venue_instruments: VenueInstrumentOut[];
  data_source_instruments: DataSourceInstrumentOut[];
}

// The 5 states of a TechnicalCapability dimension — never coerced to
// boolean, never reduced to a subset.
export type CapabilityStatus =
  'NOT_IMPLEMENTED' | 'NOT_EVALUATED' | 'SUPPORTED' | 'NOT_SUPPORTED' | 'NOT_APPLICABLE';

export interface InstrumentRef {
  instrument_id: string;
  canonical_symbol: string;
}

export interface CapabilityProviderRef {
  kind: 'venue' | 'data_source';
  id: string;
  code: string;
  display_name: string;
}

export interface TechnicalCapabilityOut {
  id: string;
  instrument: InstrumentRef;
  timeframe: TimeframeRef;
  provider: CapabilityProviderRef;
  market_data_status: CapabilityStatus;
  signal_detection_status: CapabilityStatus;
  backtest_status: CapabilityStatus;
  demo_execution_status: CapabilityStatus;
  real_execution_status: CapabilityStatus;
  settlement_status: CapabilityStatus;
  reason_unavailable: string | null;
  effective_from: string;
  effective_to: string | null;
}

export type ExecutionEnvironment = 'DEMO' | 'REAL';
export type CredentialsStatus = 'NOT_CONFIGURED' | 'CONFIGURED' | 'INVALID';
export type VenuePermissionStatus = 'NOT_EVALUATED' | 'GRANTED' | 'DENIED';
export type RegulatoryEligibilityStatus = 'NOT_EVALUATED' | 'ELIGIBLE' | 'NOT_ELIGIBLE';
export type OwnerAuthorizationStatus = 'NOT_AUTHORIZED' | 'AUTHORIZED';
// An ExecutionContext's activation status — ENABLED never implies SUPPORTED
// implies ENABLED, and NOT_CONFIGURED/SUSPENDED are distinct states, never
// presented as "blocked" or "not eligible".
export type ActivationStatus = 'NOT_CONFIGURED' | 'CONFIGURED' | 'ENABLED' | 'SUSPENDED';
export type RegulatoryRuleEffect = 'ELIGIBLE' | 'NOT_ELIGIBLE';

export interface RegulatoryRuleEvidenceOut {
  id: string;
  jurisdiction: string;
  client_classification: string | null;
  product_type_id: string | null;
  venue_id: string | null;
  effect: RegulatoryRuleEffect;
  source_citation: string;
  verified_at: string;
  effective_from: string;
  effective_to: string | null;
}

export interface ExecutionContextOut {
  id: string;
  account_key: string;
  venue: VenueOut;
  product_type: ProductTypeRef;
  execution_environment: ExecutionEnvironment;
  jurisdiction: string;
  client_classification: string;
  credentials_status: CredentialsStatus;
  venue_permission_status: VenuePermissionStatus;
  regulatory_eligibility_status: RegulatoryEligibilityStatus;
  owner_authorization_status: OwnerAuthorizationStatus;
  activation_status: ActivationStatus;
  suspension_reasons: string[] | null;
  regulatory_rules: RegulatoryRuleEvidenceOut[];
}

export interface InstrumentFilters {
  marketCode?: string;
  productTypeCode?: string;
  symbol?: string;
  timeframeCode?: string;
  isActive?: boolean;
  limit?: number;
  offset?: number;
}

export interface ActiveListFilters {
  isActive?: boolean;
  limit?: number;
  offset?: number;
}

export interface CapabilityFilters {
  instrumentId?: string;
  venueId?: string;
  dataSourceId?: string;
  timeframeId?: string;
  includeHistory?: boolean;
  limit?: number;
  offset?: number;
}

export interface ExecutionContextFilters {
  venueId?: string;
  productTypeId?: string;
  executionEnvironment?: ExecutionEnvironment;
  limit?: number;
  offset?: number;
}
