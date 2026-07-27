import { HttpErrorResponse, provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';

import { API_BASE_URL } from '../config/api.config';
import { CatalogService } from './catalog.service';
import { ExecutionContextOut, InstrumentOut, Page, TechnicalCapabilityOut } from './catalog.models';

/** Any key matching this pattern would mean a secret/credential leaked into
 * a read-only catalog contract — none of these DTOs should ever carry one. */
const SECRET_LIKE_KEY = /secret|password|token|credential|api[_-]?key|private[_-]?key/i;

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

  it('getInstruments() passes a populated page through untransformed', () => {
    let result: Page<InstrumentOut> | undefined;
    service.getInstruments().subscribe((page) => (result = page));

    const fixture: InstrumentOut = {
      instrument_id: 'i-1',
      market: { id: 'm-1', code: 'CRYPTO', display_name: 'Crypto' },
      product_type: { id: 'p-1', code: 'SPOT', display_name: 'Spot' },
      canonical_symbol: 'BTC/USDT',
      base_asset: { id: 'a-btc', code: 'BTC', display_name: 'Bitcoin' },
      quote_asset: { id: 'a-usdt', code: 'USDT', display_name: 'Tether' },
      underlying_asset: null,
      underlying_instrument_id: null,
      is_active: true,
      timeframes: [{ id: 'tf-1', code: '1m', display_name: '1 minute', duration_seconds: 60 }],
    };
    httpMock
      .expectOne(`${API_BASE_URL}/catalog/instruments`)
      .flush({ items: [fixture], total: 1, limit: 50, offset: 0 });

    expect(result?.items[0]).toEqual(fixture);
  });

  it('getInstruments() propagates an HTTP error and never emits fallback data', () => {
    let nextCalled = false;
    let receivedError: HttpErrorResponse | undefined;
    service.getInstruments().subscribe({
      next: () => (nextCalled = true),
      error: (err: HttpErrorResponse) => (receivedError = err),
    });

    httpMock
      .expectOne(`${API_BASE_URL}/catalog/instruments`)
      .flush(
        { detail: 'Internal server error' },
        new HttpErrorResponse({ status: 500, statusText: 'Internal Server Error' }),
      );

    expect(nextCalled).toBe(false);
    expect(receivedError?.status).toBe(500);
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

  it('getDataSources() only sends filters that were actually provided', () => {
    service.getDataSources({ isActive: true, limit: 10, offset: 20 }).subscribe();
    const req = httpMock.expectOne((r) => r.url === `${API_BASE_URL}/catalog/data-sources`);
    expect(req.request.params.get('is_active')).toBe('true');
    expect(req.request.params.get('limit')).toBe('10');
    expect(req.request.params.get('offset')).toBe('20');
    req.flush({ items: [], total: 0, limit: 10, offset: 20 });
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

  it('getExecutionContext() propagates a 404 and never invents a fallback context', () => {
    let nextCalled = false;
    let receivedError: HttpErrorResponse | undefined;
    service.getExecutionContext('missing-ctx').subscribe({
      next: () => (nextCalled = true),
      error: (err: HttpErrorResponse) => (receivedError = err),
    });

    httpMock
      .expectOne(`${API_BASE_URL}/execution-contexts/missing-ctx`)
      .flush(
        { detail: 'Not found' },
        new HttpErrorResponse({ status: 404, statusText: 'Not Found' }),
      );

    expect(nextCalled).toBe(false);
    expect(receivedError?.status).toBe(404);
  });

  // Architectural gap (documented, not a defect): there is no catalog UI
  // component in this repo yet — CatalogService has zero consumers
  // (see frontend/src/app/app.routes.ts, which declares no catalog route,
  // and `grep -r CatalogService frontend/src` finds only this spec file).
  // Loading/empty/error/retry states at the *component* level are therefore
  // NOT APPLICABLE for POINT1-TEST-001: there is no productive UI to exercise
  // them against, and building one is out of scope (no new business/UI
  // functionality per this task's mandate). This gap is called out in the
  // final report for a possible follow-up frontend task.

  it('an InstrumentOut fixture exposes only documented catalog fields, never credentials or secrets', () => {
    const fixture: InstrumentOut = {
      instrument_id: 'i-1',
      market: { id: 'm-1', code: 'CRYPTO', display_name: 'Crypto' },
      product_type: { id: 'p-1', code: 'SPOT', display_name: 'Spot' },
      canonical_symbol: 'BTC/USDT',
      base_asset: { id: 'a-btc', code: 'BTC', display_name: 'Bitcoin' },
      quote_asset: { id: 'a-usdt', code: 'USDT', display_name: 'Tether' },
      underlying_asset: null,
      underlying_instrument_id: null,
      is_active: true,
      timeframes: [],
    };

    expect(Object.keys(fixture).sort()).toEqual(
      [
        'instrument_id',
        'market',
        'product_type',
        'canonical_symbol',
        'base_asset',
        'quote_asset',
        'underlying_asset',
        'underlying_instrument_id',
        'is_active',
        'timeframes',
      ].sort(),
    );
    expect(Object.keys(fixture).some((key) => SECRET_LIKE_KEY.test(key))).toBe(false);
  });

  it('an ExecutionContextOut fixture exposes only status/evidence fields, never raw credentials or tokens', () => {
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
      product_type: { id: 'p-1', code: 'SPOT', display_name: 'Spot' },
      execution_environment: 'DEMO',
      jurisdiction: 'TEST_XX',
      client_classification: 'TEST_RETAIL',
      credentials_status: 'CONFIGURED',
      venue_permission_status: 'GRANTED',
      regulatory_eligibility_status: 'ELIGIBLE',
      owner_authorization_status: 'AUTHORIZED',
      activation_status: 'ENABLED',
      suspension_reasons: null,
      regulatory_rules: [],
    };

    expect(Object.keys(fixture).sort()).toEqual(
      [
        'id',
        'account_key',
        'venue',
        'product_type',
        'execution_environment',
        'jurisdiction',
        'client_classification',
        'credentials_status',
        'venue_permission_status',
        'regulatory_eligibility_status',
        'owner_authorization_status',
        'activation_status',
        'suspension_reasons',
        'regulatory_rules',
      ].sort(),
    );
    // credentials_status is a status enum (CONFIGURED/NOT_CONFIGURED/INVALID),
    // never the credential value itself — *_status fields are exempt from
    // the secret-like-key check below since they only ever carry enum tags.
    expect(['NOT_CONFIGURED', 'CONFIGURED', 'INVALID']).toContain(fixture.credentials_status);
    const secretLikeKeys = Object.keys(fixture).filter(
      (key) => !key.endsWith('_status') && SECRET_LIKE_KEY.test(key),
    );
    expect(secretLikeKeys).toEqual([]);
  });
});
