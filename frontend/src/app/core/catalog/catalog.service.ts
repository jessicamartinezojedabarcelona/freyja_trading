import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { API_BASE_URL } from '../config/api.config';
import {
  ActiveListFilters,
  CapabilityFilters,
  DataSourceOut,
  ExecutionContextFilters,
  ExecutionContextOut,
  InstrumentFilters,
  InstrumentMappingsOut,
  InstrumentOut,
  Page,
  TechnicalCapabilityOut,
  VenueOut,
} from './catalog.models';

type ParamValue = string | number | boolean | undefined;

/** Only sets a param when its value is actually provided — an omitted
 * filter must never be sent as the literal string "undefined". */
function buildParams(entries: Record<string, ParamValue>): HttpParams {
  let params = new HttpParams();
  for (const [key, value] of Object.entries(entries)) {
    if (value !== undefined) {
      params = params.set(key, String(value));
    }
  }
  return params;
}

@Injectable({ providedIn: 'root' })
export class CatalogService {
  private readonly http = inject(HttpClient);

  getInstruments(filters: InstrumentFilters = {}): Observable<Page<InstrumentOut>> {
    const params = buildParams({
      market_code: filters.marketCode,
      product_type_code: filters.productTypeCode,
      symbol: filters.symbol,
      timeframe_code: filters.timeframeCode,
      is_active: filters.isActive,
      limit: filters.limit,
      offset: filters.offset,
    });
    return this.http.get<Page<InstrumentOut>>(`${API_BASE_URL}/catalog/instruments`, { params });
  }

  getInstrument(instrumentId: string): Observable<InstrumentOut> {
    return this.http.get<InstrumentOut>(`${API_BASE_URL}/catalog/instruments/${instrumentId}`);
  }

  getInstrumentMappings(instrumentId: string): Observable<InstrumentMappingsOut> {
    return this.http.get<InstrumentMappingsOut>(
      `${API_BASE_URL}/catalog/instruments/${instrumentId}/mappings`,
    );
  }

  getVenues(filters: ActiveListFilters = {}): Observable<Page<VenueOut>> {
    const params = buildParams({
      is_active: filters.isActive,
      limit: filters.limit,
      offset: filters.offset,
    });
    return this.http.get<Page<VenueOut>>(`${API_BASE_URL}/catalog/venues`, { params });
  }

  getDataSources(filters: ActiveListFilters = {}): Observable<Page<DataSourceOut>> {
    const params = buildParams({
      is_active: filters.isActive,
      limit: filters.limit,
      offset: filters.offset,
    });
    return this.http.get<Page<DataSourceOut>>(`${API_BASE_URL}/catalog/data-sources`, { params });
  }

  getCapabilities(filters: CapabilityFilters = {}): Observable<Page<TechnicalCapabilityOut>> {
    const params = buildParams({
      instrument_id: filters.instrumentId,
      venue_id: filters.venueId,
      data_source_id: filters.dataSourceId,
      timeframe_id: filters.timeframeId,
      include_history: filters.includeHistory,
      limit: filters.limit,
      offset: filters.offset,
    });
    return this.http.get<Page<TechnicalCapabilityOut>>(`${API_BASE_URL}/capabilities`, {
      params,
    });
  }

  getCapability(capabilityId: string): Observable<TechnicalCapabilityOut> {
    return this.http.get<TechnicalCapabilityOut>(`${API_BASE_URL}/capabilities/${capabilityId}`);
  }

  getExecutionContexts(
    filters: ExecutionContextFilters = {},
  ): Observable<Page<ExecutionContextOut>> {
    const params = buildParams({
      venue_id: filters.venueId,
      product_type_id: filters.productTypeId,
      execution_environment: filters.executionEnvironment,
      limit: filters.limit,
      offset: filters.offset,
    });
    return this.http.get<Page<ExecutionContextOut>>(`${API_BASE_URL}/execution-contexts`, {
      params,
    });
  }

  getExecutionContext(contextId: string): Observable<ExecutionContextOut> {
    return this.http.get<ExecutionContextOut>(`${API_BASE_URL}/execution-contexts/${contextId}`);
  }
}
