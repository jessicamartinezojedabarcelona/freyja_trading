import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';

import { API_BASE_URL } from '../config/api.config';
import { MarketDataService } from './market-data.service';
import { INSTRUMENT_ID, makeSeries } from './market-data.testing';

describe('MarketDataService', () => {
  let service: MarketDataService;
  let httpMock: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    service = TestBed.inject(MarketDataService);
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    httpMock.verify();
  });

  it('asks only for what it was given', () => {
    let received: unknown;
    service
      .getCandles({ instrumentId: INSTRUMENT_ID, dataSourceCode: 'BINANCE' })
      .subscribe((series) => (received = series));

    const request = httpMock.expectOne((r) => r.url === `${API_BASE_URL}/market-data/candles`);
    expect(request.request.method).toBe('GET');
    expect(request.request.params.keys().sort()).toEqual(['data_source_code', 'instrument_id']);
    expect(request.request.params.get('instrument_id')).toBe(INSTRUMENT_ID);
    expect(request.request.params.get('data_source_code')).toBe('BINANCE');
    // An omitted period must not be sent, so the backend applies its own 1m default.
    expect(request.request.params.has('timeframe_code')).toBe(false);

    const body = makeSeries();
    request.flush(body);
    expect(received).toEqual(body);
  });

  it('sends every provided filter under its API name and never the string "undefined"', () => {
    service
      .getCandles({
        instrumentId: INSTRUMENT_ID,
        dataSourceCode: 'BINANCE',
        timeframeCode: '5m',
        start: '2026-09-24T12:00:00Z',
        end: '2026-09-24T13:00:00Z',
        limit: 200,
      })
      .subscribe();

    const request = httpMock.expectOne((r) => r.url === `${API_BASE_URL}/market-data/candles`);
    expect(request.request.params.keys().sort()).toEqual([
      'data_source_code',
      'end',
      'instrument_id',
      'limit',
      'start',
      'timeframe_code',
    ]);
    expect(request.request.params.get('timeframe_code')).toBe('5m');
    expect(request.request.params.get('limit')).toBe('200');
    expect(request.request.params.get('start')).toBe('2026-09-24T12:00:00Z');
    expect(request.request.urlWithParams).not.toContain('undefined');
    request.flush(makeSeries());
  });

  it('propagates HTTP errors to the caller', () => {
    let status: number | undefined;
    service
      .getCandles({ instrumentId: INSTRUMENT_ID, dataSourceCode: 'KRAKEN' })
      .subscribe({ error: (error: { status: number }) => (status = error.status) });

    httpMock
      .expectOne((r) => r.url === `${API_BASE_URL}/market-data/candles`)
      .flush(
        { detail: 'Fuente de datos no encontrada.' },
        { status: 404, statusText: 'Not Found' },
      );
    expect(status).toBe(404);
  });
});
