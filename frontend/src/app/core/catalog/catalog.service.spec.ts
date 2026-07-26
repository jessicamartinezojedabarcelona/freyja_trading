import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';

import { API_BASE_URL } from '../config/api.config';
import { CatalogService } from './catalog.service';
import { ExecutionContextOut, Page, TechnicalCapabilityOut } from './catalog.models';

describe('CatalogService', () => {
  let service: CatalogService;
  let httpMock: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    service = TestBed.inject(CatalogService);
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    httpMock.verify();
  });

  it('getInstruments() calls the catalog instruments endpoint with no params by default', () => {
    service.getInstruments().subscribe();
    const req = httpMock.expectOne(`${API_BASE_URL}/catalog/instruments`);
    expect(req.request.method).toBe('GET');
    expect(req.request.params.keys().length).toBe(0);
    req.flush({ items: [], total: 0, limit: 50, offset: 0 });
  });

  it('getInstruments() only sends filters that were actually provided', () => {
    service.getInstruments({ marketCode: 'CRYPTO', isActive: true }).subscribe();
    const req = httpMock.expectOne((r) => r.url === `${API_BASE_URL}/catalog/instruments`);
    expect(req.request.params.get('market_code')).toBe('CRYPTO');
    expect(req.request.params.get('is_active')).toBe('true');
    expect(req.request.params.has('product_type_code')).toBe(false);
    expect(req.request.params.has('symbol')).toBe(false);
    expect(req.request.params.has('timeframe_code')).toBe(false);
    req.flush({ items: [], total: 0, limit: 50, offset: 0 });
  });

  it('an empty catalog page is never replaced by mock data', () => {
    let result: Page<unknown> | undefined;
    service.getInstruments().subscribe((page) => (result = page));
    httpMock
      .expectOne(`${API_BASE_URL}/catalog/instruments`)
      .flush({ items: [], total: 0, limit: 50, offset: 0 });
    expect(result).toEqual({ items: [], total: 0, limit: 50, offset: 0 });
  });

  it('getInstrument() calls the instrument-by-id endpoint', () => {
    service.getInstrument('instrument-1').subscribe();
    const req = httpMock.expectOne(`${API_BASE_URL}/catalog/instruments/instrument-1`);
    expect(req.request.method).toBe('GET');
    req.flush({});
  });

  it('getInstrumentMappings() calls the mappings sub-resource', () => {
    service.getInstrumentMappings('instrument-1').subscribe();
    const req = httpMock.expectOne(`${API_BASE_URL}/catalog/instruments/instrument-1/mappings`);
    expect(req.request.method).toBe('GET');
    req.flush({
      instrument_id: 'instrument-1',
      venue_instruments: [],
      data_source_instruments: [],
    });
  });

  it('getVenues() calls the venues endpoint', () => {
    service.getVenues({ isActive: false }).subscribe();
    const req = httpMock.expectOne((r) => r.url === `${API_BASE_URL}/catalog/venues`);
    expect(req.request.params.get('is_active')).toBe('false');
    req.flush({ items: [], total: 0, limit: 50, offset: 0 });
  });

  it('getDataSources() calls the data-sources endpoint', () => {
    service.getDataSources().subscribe();
    const req = httpMock.expectOne(`${API_BASE_URL}/catalog/data-sources`);
    expect(req.request.method).toBe('GET');
    req.flush({ items: [], total: 0, limit: 50, offset: 0 });
  });

  it('getCapabilities() forwards include_history and preserves all 5 statuses untransformed', () => {
    let result: Page<TechnicalCapabilityOut> | undefined;
    service.getCapabilities({ instrumentId: 'i-1', includeHistory: true }).subscribe((page) => {
      result = page;
    });
    const req = httpMock.expectOne((r) => r.url === `${API_BASE_URL}/capabilities`);
    expect(req.request.params.get('instrument_id')).toBe('i-1');
    expect(req.request.params.get('include_history')).toBe('true');

    const fixture: TechnicalCapabilityOut = {
      id: 'cap-1',
      instrument: { instrument_id: 'i-1', canonical_symbol: 'BTC/USDT' },
      timeframe: { id: 'tf-1', code: '1m', display_name: '1 minute', duration_seconds: 60 },
      provider: { kind: 'venue', id: 'v-1', code: 'TEST', display_name: 'Test' },
      market_data_status: 'SUPPORTED',
      signal_detection_status: 'NOT_IMPLEMENTED',
      backtest_status: 'NOT_EVALUATED',
      demo_execution_status: 'NOT_SUPPORTED',
      real_execution_status: 'NOT_APPLICABLE',
      settlement_status: 'NOT_APPLICABLE',
      // reason_unavailable is required whenever any dimension is
      // NOT_SUPPORTED (ck_freyja2_technical_capabilities_reason_iff_not_supported).
      reason_unavailable: 'TEST fixture reason — not real supportability evidence',
      effective_from: '2026-01-01T00:00:00Z',
      effective_to: null,
    };
    req.flush({ items: [fixture], total: 1, limit: 50, offset: 0 });

    expect(result?.items[0]).toEqual(fixture);
  });

  it('getCapability() calls the capability-by-id endpoint', () => {
    service.getCapability('cap-1').subscribe();
    const req = httpMock.expectOne(`${API_BASE_URL}/capabilities/cap-1`);
    expect(req.request.method).toBe('GET');
    req.flush({});
  });

  it('getExecutionContexts() forwards the DEMO/REAL filter and preserves activation states', () => {
    let result: Page<ExecutionContextOut> | undefined;
    service.getExecutionContexts({ executionEnvironment: 'REAL' }).subscribe((page) => {
      result = page;
    });
    const req = httpMock.expectOne((r) => r.url === `${API_BASE_URL}/execution-contexts`);
    expect(req.request.params.get('execution_environment')).toBe('REAL');

    const fixture: ExecutionContextOut = {
      id: 'ctx-1',
      account_key: 'ACC_1',
      venue: {
        id: 'v-1',
        code: 'TEST',
        display_name: 'Test',
        venue_type: 'EXCHANGE',
        is_active: true,
      },
      product_type: { id: 'p-1', code: 'BINARY_OPTION', display_name: 'Binary option' },
      execution_environment: 'REAL',
      jurisdiction: 'TEST_XX',
      client_classification: 'TEST_RETAIL',
      credentials_status: 'NOT_CONFIGURED',
      venue_permission_status: 'NOT_EVALUATED',
      regulatory_eligibility_status: 'NOT_EVALUATED',
      owner_authorization_status: 'NOT_AUTHORIZED',
      activation_status: 'SUSPENDED',
      suspension_reasons: ['TEST reason'],
      regulatory_rules: [
        {
          id: 'rule-general',
          jurisdiction: 'TEST_XX',
          client_classification: null,
          product_type_id: null,
          venue_id: null,
          effect: 'NOT_ELIGIBLE',
          source_citation: 'TEST general rule',
          verified_at: '2026-01-01T00:00:00Z',
          effective_from: '2026-01-01T00:00:00Z',
          effective_to: null,
        },
        {
          id: 'rule-scoped',
          jurisdiction: 'TEST_XX',
          client_classification: 'TEST_RETAIL',
          product_type_id: 'p-1',
          venue_id: 'v-1',
          effect: 'NOT_ELIGIBLE',
          source_citation: 'TEST product-and-venue-scoped rule',
          verified_at: '2026-01-01T00:00:00Z',
          effective_from: '2026-01-01T00:00:00Z',
          effective_to: null,
        },
      ],
    };
    req.flush({ items: [fixture], total: 1, limit: 50, offset: 0 });

    expect(result?.items[0]).toEqual(fixture);
    // NOT_CONFIGURED/NOT_EVALUATED must reach the caller as-is — never
    // silently upgraded/downgraded to NOT_ELIGIBLE or a boolean.
    expect(result?.items[0].credentials_status).toBe('NOT_CONFIGURED');
    expect(result?.items[0].regulatory_eligibility_status).toBe('NOT_EVALUATED');
    // product_type_id/venue_id must pass through untransformed, distinguishing
    // a general rule (both null) from one scoped to a product and venue.
    const [general, scoped] = result?.items[0].regulatory_rules ?? [];
    expect(general.product_type_id).toBeNull();
    expect(general.venue_id).toBeNull();
    expect(scoped.product_type_id).toBe('p-1');
    expect(scoped.venue_id).toBe('v-1');
  });

  it('getExecutionContext() calls the context-by-id endpoint', () => {
    service.getExecutionContext('ctx-1').subscribe();
    const req = httpMock.expectOne(`${API_BASE_URL}/execution-contexts/ctx-1`);
    expect(req.request.method).toBe('GET');
    req.flush({});
  });
});
