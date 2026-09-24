import { provideHttpClient } from '@angular/common/http';
import {
  HttpTestingController,
  TestRequest,
  provideHttpClientTesting,
} from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { Router, provideRouter } from '@angular/router';
import { RouterTestingHarness } from '@angular/router/testing';

import { InstrumentMappingsOut, InstrumentOut } from '../../core/catalog/catalog.models';
import { API_BASE_URL } from '../../core/config/api.config';
import { CandleSeriesOut } from '../../core/market-data/market-data.models';
import {
  INSTRUMENT_ID,
  OTHER_INSTRUMENT_ID,
  makeCandle,
  makeInstrument,
  makeMappings,
  makeSeries,
  makeSourceMapping,
} from '../../core/market-data/market-data.testing';
import { ChartData } from './chart-data';
import { CHART_FACTORY, ChartHandle } from './chart-handle';
import { MarketsPage, PAGE_SIZE } from './markets.page';

const CANDLES_URL = `${API_BASE_URL}/market-data/candles`;
const INSTRUMENTS_URL = `${API_BASE_URL}/catalog/instruments`;

const BTC = makeInstrument();
const ETH = makeInstrument({
  instrument_id: OTHER_INSTRUMENT_ID,
  canonical_symbol: 'ETH/USDT',
});
const BINARY = makeInstrument({
  instrument_id: 'binary-1',
  canonical_symbol: 'BTC',
  market: { id: 'm-crypto', code: 'CRYPTO', display_name: 'Crypto' },
  product_type: { id: 'p-bin', code: 'BINARY_OPTION', display_name: 'Binary option' },
});
const FOREX = makeInstrument({
  instrument_id: 'forex-1',
  canonical_symbol: 'EUR/USD',
  market: { id: 'm-forex', code: 'FOREX', display_name: 'Forex' },
});

class FakeChart implements ChartHandle {
  readonly drawn: { data: ChartData; resetView: boolean }[] = [];
  destroyed = 0;
  setData(data: ChartData, options: { resetView: boolean }): void {
    this.drawn.push({ data, resetView: options.resetView });
  }
  destroy(): void {
    this.destroyed += 1;
  }
}

const tick = () => new Promise((resolve) => setTimeout(resolve, 0));
const squash = (element: Element | null | undefined) =>
  (element?.textContent ?? '').replace(/\s+/g, ' ').trim();

describe('MarketsPage', () => {
  let httpMock: HttpTestingController;
  let harness: RouterTestingHarness;
  let chart: FakeChart;
  let chartsCreated: number;

  const root = () => harness.fixture.nativeElement as HTMLElement;
  const text = () => squash(root());

  async function settle(): Promise<void> {
    await harness.fixture.whenStable();
    await tick();
    harness.detectChanges();
  }

  async function open(url: string): Promise<void> {
    chart = new FakeChart();
    chartsCreated = 0;
    TestBed.configureTestingModule({
      providers: [
        provideRouter([
          { path: 'mercados', component: MarketsPage },
          { path: 'mercados/:instrumentId', component: MarketsPage },
        ]),
        provideHttpClient(),
        provideHttpClientTesting(),
        {
          provide: CHART_FACTORY,
          useValue: () => {
            chartsCreated += 1;
            return Promise.resolve(chart);
          },
        },
      ],
    });
    httpMock = TestBed.inject(HttpTestingController);
    harness = await RouterTestingHarness.create();
    await harness.navigateByUrl(url, MarketsPage);
  }

  function flushInstruments(items: InstrumentOut[] = [BTC, ETH], total = items.length): void {
    httpMock
      .expectOne((r) => r.url === INSTRUMENTS_URL)
      .flush({ items, total, limit: 200, offset: 0 });
  }

  function flushDetail(
    instrument: InstrumentOut = BTC,
    mappings: InstrumentMappingsOut = makeMappings(undefined, instrument.instrument_id),
  ): void {
    httpMock
      .expectOne(`${API_BASE_URL}/catalog/instruments/${instrument.instrument_id}`)
      .flush(instrument);
    httpMock
      .expectOne(`${API_BASE_URL}/catalog/instruments/${instrument.instrument_id}/mappings`)
      .flush(mappings);
  }

  function candlesRequest(): TestRequest {
    return httpMock.expectOne((r) => r.url === CANDLES_URL);
  }

  /** Opens an instrument and answers every request it makes. */
  async function openLoaded(
    url = `/mercados/${INSTRUMENT_ID}`,
    series: CandleSeriesOut = makeSeries(),
  ): Promise<TestRequest> {
    await open(url);
    flushInstruments();
    flushDetail();
    const request = candlesRequest();
    request.flush(series);
    await settle();
    return request;
  }

  afterEach(() => {
    httpMock.verify();
  });

  describe('before an instrument is chosen', () => {
    it('invites the user to choose one and requests nothing else', async () => {
      await open('/mercados');
      flushInstruments();
      await settle();

      expect(text()).toContain('Elige un instrumento');
      expect(root().querySelector('app-candle-chart')).toBeNull();
      expect(chartsCreated).toBe(0);
      const names = [...root().querySelectorAll('.instrument .symbol')].map((e) => squash(e));
      expect(names).toEqual(['BTC/USDT', 'ETH/USDT']);
    });

    it('filters the list by what the user types', async () => {
      await open('/mercados');
      flushInstruments([BTC, ETH, BINARY, FOREX]);
      await settle();

      const box = root().querySelector<HTMLInputElement>('input[type="search"]')!;
      box.value = 'eur';
      box.dispatchEvent(new Event('input'));
      harness.detectChanges();

      expect([...root().querySelectorAll('.instrument .symbol')].map((e) => squash(e))).toEqual([
        'EUR/USD',
      ]);
    });

    it('filters the list by market, and says when nothing matches', async () => {
      await open('/mercados');
      flushInstruments([BTC, FOREX]);
      await settle();

      const select = root().querySelector<HTMLSelectElement>('select')!;
      expect([...select.options].map((o) => o.textContent?.trim())).toEqual([
        'Todos',
        'Cripto',
        'Forex',
      ]);
      select.value = 'FOREX';
      select.dispatchEvent(new Event('change'));
      harness.detectChanges();
      expect([...root().querySelectorAll('.instrument .symbol')].map((e) => squash(e))).toEqual([
        'EUR/USD',
      ]);

      const box = root().querySelector<HTMLInputElement>('input[type="search"]')!;
      box.value = 'zzz';
      box.dispatchEvent(new Event('input'));
      harness.detectChanges();
      expect(text()).toContain('Ningún instrumento coincide con el filtro.');
    });

    it('says how many instruments are not shown when the catalog is larger than a page', async () => {
      await open('/mercados');
      flushInstruments([BTC, ETH], 340);
      await settle();
      expect(text()).toContain('Mostrando 2 de 340 instrumentos.');
    });

    it('reports a failure to load the list instead of an empty one', async () => {
      await open('/mercados');
      httpMock
        .expectOne((r) => r.url === INSTRUMENTS_URL)
        .flush({}, { status: 500, statusText: 'Server Error' });
      await settle();

      expect(root().querySelector('[role="alert"]')?.textContent).toContain(
        'No se pudo cargar la lista de instrumentos',
      );
    });
  });

  describe('with an instrument in the URL', () => {
    it('loads the instrument, its sources and 1-minute candles by default', async () => {
      const request = await openLoaded();

      expect(request.request.params.get('instrument_id')).toBe(INSTRUMENT_ID);
      expect(request.request.params.get('data_source_code')).toBe('BINANCE');
      expect(request.request.params.get('timeframe_code')).toBe('1m');
      expect(request.request.params.get('limit')).toBe(String(PAGE_SIZE));

      expect(squash(root().querySelector('.heading h2'))).toBe('BTC/USDT');
      expect(text()).toContain('Cripto · Spot');
      const pressed = root().querySelector('app-timeframe-picker [aria-pressed="true"]');
      expect(squash(pressed)).toBe('1m');
    });

    it('draws the closed candles it received, and only after the chart is ready', async () => {
      await openLoaded();

      expect(chartsCreated).toBe(1);
      expect(chart.drawn.at(-1)?.data.candles).toHaveLength(3);
      expect(chart.drawn.at(-1)?.resetView).toBe(true);
    });

    it('states unit, zone, that only closed candles are shown, and credits the chart library', async () => {
      await openLoaded();

      const note = squash(root().querySelector('.chart-note'));
      expect(note).toContain('Hora en UTC');
      expect(note).toContain('Solo velas cerradas');
      const link = root().querySelector<HTMLAnchorElement>('.chart-note a')!;
      expect(link.href).toBe('https://www.tradingview.com/');
      expect(link.rel).toContain('noopener');
      expect(link.textContent).toContain('TradingView');
    });

    it('describes the graphic in words for assistive technology', async () => {
      await openLoaded();

      const label = root().querySelector('[role="img"]')?.getAttribute('aria-label') ?? '';
      expect(label).toContain('BTC/USDT');
      expect(label).toContain('periodo 1m');
      expect(label).toContain('fuente Binance');
      expect(label).toContain('3 velas cerradas');
      expect(label).toContain('UTC');
      expect(label).toContain('Último cierre 101');
    });

    it('shows where the data comes from and how current it is', async () => {
      await openLoaded();

      const status = squash(root().querySelector('app-series-status'));
      expect(status).toContain('Binance');
      expect(status).toContain('Al día');
      expect(status).toContain('Calidad correcta');
    });

    it('honours the period and source in the URL', async () => {
      const request = await openLoaded(`/mercados/${INSTRUMENT_ID}?tf=5m&source=BINANCE`);

      expect(request.request.params.get('timeframe_code')).toBe('5m');
      expect(squash(root().querySelector('app-timeframe-picker [aria-pressed="true"]'))).toBe('5m');
    });

    it('falls back to 1m when the requested period is not enabled for the instrument', async () => {
      const request = await openLoaded(`/mercados/${INSTRUMENT_ID}?tf=30s`);

      expect(request.request.params.get('timeframe_code')).toBe('1m');
    });

    it('never offers an unavailable period as selectable', async () => {
      await openLoaded();

      const thirtySeconds = [...root().querySelectorAll<HTMLButtonElement>('button.period')].find(
        (b) => squash(b).includes('30seg'),
      )!;
      expect(thirtySeconds.disabled).toBe(true);
    });
  });

  describe('when there is nothing to draw', () => {
    it('explains that no source publishes candles for the instrument, without fetching any', async () => {
      await open(`/mercados/${INSTRUMENT_ID}`);
      flushInstruments();
      flushDetail(
        BTC,
        makeMappings([
          makeSourceMapping('BINANCE', 'Binance', { purpose: 'SETTLEMENT' }),
          makeSourceMapping('OTHER', 'Otro', { is_active: false }),
        ]),
      );
      await settle();

      expect(text()).toContain('Este instrumento aún no tiene velas');
      expect(root().querySelector('app-candle-chart')).toBeNull();
      expect(chartsCreated).toBe(0);
      httpMock.expectNone((r) => r.url === CANDLES_URL);
    });

    it('explains that the instrument has no period enabled, without fetching any', async () => {
      const bare = makeInstrument({ timeframes: [] });
      await open(`/mercados/${INSTRUMENT_ID}`);
      flushInstruments();
      flushDetail(bare);
      await settle();

      expect(text()).toContain('Este instrumento aún no tiene velas');
      httpMock.expectNone((r) => r.url === CANDLES_URL);
    });

    it('shows an empty state, never an example chart, when nothing is stored yet', async () => {
      await openLoaded(
        `/mercados/${INSTRUMENT_ID}`,
        makeSeries({
          candles: [],
          quality: 'UNAVAILABLE',
          issues: [{ code: 'NO_DATA', detail: 'x' }],
          freshness: {
            status: 'NO_DATA',
            checked_at: '2026-09-24T12:04:00Z',
            latest_open_time: null,
            latest_close_time: null,
            latest_received_at: null,
          },
          provider: null,
        }),
      );

      expect(text()).toContain('Todavía no hay velas guardadas');
      expect(root().querySelector('app-candle-chart')).toBeNull();
      expect(root().querySelector('details.table-alt')).toBeNull();
      expect(chartsCreated).toBe(0);
      const status = root().querySelector('app-series-status');
      expect(status?.querySelector('[role="alert"]')).not.toBeNull();
      expect(squash(status)).toContain('Sin datos');
    });
  });

  describe('data quality', () => {
    it('draws degraded data but announces it before anything else', async () => {
      await openLoaded(
        `/mercados/${INSTRUMENT_ID}`,
        makeSeries({
          quality: 'DEGRADED',
          issues: [{ code: 'GAP', detail: 'x' }],
          gaps: [{ after_open_time: '2026-09-24T12:01:00Z', missing: 2 }],
        }),
      );

      expect(chart.drawn).not.toHaveLength(0);
      const banner = root().querySelector('app-series-status .banner');
      expect(banner?.getAttribute('role')).toBe('status');
      expect(squash(banner)).toContain('Calidad degradada');
      expect(text()).toContain('2 velas tras la de');
    });
  });

  describe('when loading fails', () => {
    it('shows an understandable error and retries on demand', async () => {
      await open(`/mercados/${INSTRUMENT_ID}`);
      flushInstruments();
      flushDetail();
      candlesRequest().flush({}, { status: 500, statusText: 'Server Error' });
      await settle();

      const alert = root().querySelector('.content [role="alert"]');
      expect(squash(alert)).toContain('No se pudieron cargar las velas. Inténtalo de nuevo.');
      expect(squash(alert)).not.toContain('500');
      expect(root().querySelector('app-candle-chart')).toBeNull();

      root().querySelector<HTMLButtonElement>('.alert .btn')!.click();
      candlesRequest().flush(makeSeries());
      await settle();

      expect(root().querySelector('.content [role="alert"]')).toBeNull();
      expect(chart.drawn).not.toHaveLength(0);
    });

    it('says the connection failed when the server cannot be reached', async () => {
      await open(`/mercados/${INSTRUMENT_ID}`);
      flushInstruments();
      flushDetail();
      candlesRequest().error(new ProgressEvent('error'));
      await settle();

      expect(text()).toContain('No se pudo conectar con el servidor');
    });

    it('says the instrument or source was not found', async () => {
      await open(`/mercados/${INSTRUMENT_ID}`);
      flushInstruments();
      httpMock
        .expectOne(`${API_BASE_URL}/catalog/instruments/${INSTRUMENT_ID}`)
        .flush({ detail: 'Instrumento no encontrado.' }, { status: 404, statusText: 'Not Found' });
      // The instrument and its mappings are fetched together: once one fails, the
      // other is abandoned instead of being left running.
      const mappings = httpMock.match(
        `${API_BASE_URL}/catalog/instruments/${INSTRUMENT_ID}/mappings`,
      );
      expect(mappings.every((r) => r.cancelled)).toBe(true);
      await settle();

      expect(text()).toContain('No se encontró ese instrumento o esa fuente de datos.');
      expect(root().querySelector('.heading')).toBeNull();
    });
  });

  describe('last close', () => {
    async function withCloses(previous: string, last: string): Promise<HTMLElement> {
      await openLoaded(
        `/mercados/${INSTRUMENT_ID}`,
        makeSeries({
          candles: [makeCandle(0, { close: previous }), makeCandle(1, { close: last })],
        }),
      );
      return root().querySelector<HTMLElement>('.last-close')!;
    }

    it('rising: arrow, wording and price colour class agree', async () => {
      const close = await withCloses('100.5', '101');
      expect(squash(close)).toContain('▲ 101');
      expect(squash(close)).toContain('sube respecto a la vela anterior');
      expect(close.querySelector('.price--up')).not.toBeNull();
    });

    it('falling: arrow and wording, not just a colour', async () => {
      const close = await withCloses('101', '100.5');
      expect(squash(close)).toContain('▼ 100.5');
      expect(squash(close)).toContain('baja respecto a la vela anterior');
      expect(close.querySelector('.price--down')).not.toBeNull();
    });

    it('unchanged', async () => {
      const close = await withCloses('101', '101.0');
      expect(squash(close)).toContain('=');
      expect(squash(close)).toContain('sin cambio respecto a la vela anterior');
    });

    it('decides on the exact digits, not on floats', async () => {
      // As floats these two are the same number; as decimals the second is larger.
      expect(Number('0.1')).toBe(Number('0.10000000000000001'));
      const close = await withCloses('0.1', '0.10000000000000001');
      expect(squash(close)).toContain('▲');
    });
  });

  describe('the table alternative', () => {
    it('lists the latest 20 candles, newest first, with the zone in its caption', async () => {
      const many = Array.from({ length: 25 }, (_, i) => makeCandle(i));
      await openLoaded(`/mercados/${INSTRUMENT_ID}`, makeSeries({ candles: many }));

      const details = root().querySelector('details.table-alt')!;
      expect(squash(details.querySelector('summary'))).toBe('Ver las últimas 20 velas como tabla');
      const rows = [...details.querySelectorAll('tbody tr')];
      expect(rows).toHaveLength(20);
      expect(squash(rows[0].querySelector('th'))).toContain('12:24:00 UTC');
      expect(squash(rows[19].querySelector('th'))).toContain('12:05:00 UTC');
      expect(squash(details.querySelector('caption'))).toContain('BTC/USDT');
      expect(squash(details.querySelector('caption'))).toContain('hora UTC');
      const headers = [...details.querySelectorAll('thead th')].map((h) => squash(h));
      expect(headers).toEqual([
        'Abre (UTC)',
        'Apertura',
        'Máximo',
        'Mínimo',
        'Cierre',
        'Volumen',
        'Calidad',
      ]);
    });

    it('shows the exact strings from the API', async () => {
      await openLoaded(
        `/mercados/${INSTRUMENT_ID}`,
        makeSeries({ candles: [makeCandle(0, { open: '84805.61000001', volume: '0.00012' })] }),
      );
      const cells = [...root().querySelectorAll('tbody tr td')].map((c) => squash(c));
      expect(cells).toContain('84805.61000001');
      expect(cells).toContain('0.00012');
    });
  });

  describe('changing the selection', () => {
    it('changing the period updates the URL and reloads only the candles', async () => {
      await openLoaded();
      const router = TestBed.inject(Router);

      [...root().querySelectorAll<HTMLButtonElement>('button.period')]
        .find((b) => squash(b) === '15m')!
        .click();
      await settle();
      const request = candlesRequest(); // no catalog requests: the instrument is cached
      request.flush(makeSeries({ timeframe_code: '15m' }));
      await settle();

      expect(request.request.params.get('timeframe_code')).toBe('15m');
      expect(router.url).toContain('tf=15m');
      expect(squash(root().querySelector('app-timeframe-picker [aria-pressed="true"]'))).toBe(
        '15m',
      );
    });

    it('changing the instrument keeps the period and drops the source', async () => {
      await openLoaded(`/mercados/${INSTRUMENT_ID}?tf=5m&source=BINANCE`);
      const router = TestBed.inject(Router);

      [...root().querySelectorAll<HTMLButtonElement>('.instrument')]
        .find((b) => squash(b).startsWith('ETH/USDT'))!
        .click();
      await settle();
      httpMock.expectOne(`${API_BASE_URL}/catalog/instruments/${OTHER_INSTRUMENT_ID}`).flush(ETH);
      httpMock
        .expectOne(`${API_BASE_URL}/catalog/instruments/${OTHER_INSTRUMENT_ID}/mappings`)
        .flush(makeMappings(undefined, OTHER_INSTRUMENT_ID));
      const request = candlesRequest();
      request.flush(makeSeries({ instrument_id: OTHER_INSTRUMENT_ID, timeframe_code: '5m' }));
      await settle();

      expect(request.request.params.get('instrument_id')).toBe(OTHER_INSTRUMENT_ID);
      expect(request.request.params.get('timeframe_code')).toBe('5m');
      expect(router.url).toContain(`/mercados/${OTHER_INSTRUMENT_ID}`);
      expect(router.url).toContain('tf=5m');
      expect(router.url).not.toContain('source=');
      expect(squash(root().querySelector('.heading h2'))).toBe('ETH/USDT');
      expect(root().querySelector('.instrument--active .symbol')?.textContent).toContain(
        'ETH/USDT',
      );
    });

    it('lets the user pick between several sources, and none when there is only one', async () => {
      await openLoaded();
      expect(root().querySelector('.field--inline select')).toBeNull();

      TestBed.resetTestingModule();
      await open(`/mercados/${INSTRUMENT_ID}`);
      flushInstruments();
      flushDetail(
        BTC,
        makeMappings([
          makeSourceMapping('BINANCE', 'Binance'),
          makeSourceMapping('BROKER_X', 'Broker X'),
        ]),
      );
      candlesRequest().flush(makeSeries());
      await settle();

      const select = root().querySelector<HTMLSelectElement>('.field--inline select')!;
      expect([...select.options].map((o) => o.textContent?.trim())).toEqual([
        'Binance',
        'Broker X',
      ]);

      select.value = 'BROKER_X';
      select.dispatchEvent(new Event('change'));
      await settle();
      const request = candlesRequest();
      request.flush(makeSeries({ data_source_code: 'BROKER_X' }));
      await settle();

      expect(request.request.params.get('data_source_code')).toBe('BROKER_X');
      expect(squash(root().querySelector('app-series-status'))).toContain('Broker X');
    });

    it('applies only the latest choice when the user changes their mind quickly', async () => {
      await open(`/mercados/${INSTRUMENT_ID}`);
      flushInstruments();
      const staleRequests = [
        ...httpMock.match(`${API_BASE_URL}/catalog/instruments/${INSTRUMENT_ID}`),
        ...httpMock.match(`${API_BASE_URL}/catalog/instruments/${INSTRUMENT_ID}/mappings`),
      ];

      await harness.navigateByUrl(`/mercados/${OTHER_INSTRUMENT_ID}`, MarketsPage);
      flushDetail(ETH);
      candlesRequest().flush(makeSeries({ instrument_id: OTHER_INSTRUMENT_ID }));
      await settle();

      expect(staleRequests.every((r) => r.cancelled)).toBe(true);
      expect(squash(root().querySelector('.heading h2'))).toBe('ETH/USDT');
      expect(chart.drawn).not.toHaveLength(0);
    });
  });

  describe('older candles', () => {
    it('asks for candles before the oldest one shown and keeps the view where it was', async () => {
      await openLoaded();
      const oldestOpen = makeCandle(0).open_time;

      root().querySelector<HTMLButtonElement>('.chart-actions .btn')!.click();
      const request = candlesRequest();
      expect(request.request.params.get('end')).toBe(oldestOpen);
      expect(request.request.params.get('limit')).toBe(String(PAGE_SIZE));
      expect(request.request.params.get('instrument_id')).toBe(INSTRUMENT_ID);
      request.flush(makeSeries({ candles: [makeCandle(-2), makeCandle(-1)] }));
      await settle();

      const last = chart.drawn.at(-1)!;
      expect(last.data.candles).toHaveLength(5);
      const times = last.data.candles.map((c) => c.time);
      expect(times).toEqual([...times].sort((a, b) => a - b));
      expect(last.resetView).toBe(false);
    });

    it('says there is nothing older once a page comes back short', async () => {
      await openLoaded();

      root().querySelector<HTMLButtonElement>('.chart-actions .btn')!.click();
      candlesRequest().flush(makeSeries({ candles: [makeCandle(-1)] }));
      await settle();

      expect(text()).toContain('No hay velas anteriores guardadas.');
      expect(text()).not.toContain('Cargar velas anteriores');
    });

    it('keeps offering more while full pages keep coming', async () => {
      await openLoaded();
      const full = Array.from({ length: PAGE_SIZE }, (_, i) => makeCandle(-PAGE_SIZE + i));

      root().querySelector<HTMLButtonElement>('.chart-actions .btn')!.click();
      candlesRequest().flush(makeSeries({ candles: full }));
      await settle();

      expect(text()).toContain('Cargar velas anteriores');
      expect(chart.drawn.at(-1)?.data.candles).toHaveLength(PAGE_SIZE + 3);
    });

    it('reports a failure without losing what is already drawn', async () => {
      await openLoaded();

      root().querySelector<HTMLButtonElement>('.chart-actions .btn')!.click();
      candlesRequest().flush({}, { status: 500, statusText: 'Server Error' });
      await settle();

      expect(text()).toContain('No se pudieron cargar las velas anteriores.');
      expect(chart.drawn.at(-1)?.data.candles).toHaveLength(3);
    });

    it('does not start a second request while one is running', async () => {
      await openLoaded();
      const button = root().querySelector<HTMLButtonElement>('.chart-actions .btn')!;

      button.click();
      harness.detectChanges();
      expect(button.disabled).toBe(true);
      button.click();
      const pending = httpMock.match((r) => r.url === CANDLES_URL);
      expect(pending).toHaveLength(1);
      pending[0].flush(makeSeries({ candles: [] }));
      await settle();
    });
  });

  describe('refreshing', () => {
    it('reloads the latest candles on demand', async () => {
      await openLoaded();

      [...root().querySelectorAll<HTMLButtonElement>('.chart-actions .btn')]
        .find((b) => squash(b) === 'Actualizar')!
        .click();
      candlesRequest().flush(
        makeSeries({ candles: [makeCandle(0), makeCandle(1), makeCandle(2), makeCandle(3)] }),
      );
      await settle();

      expect(chart.drawn.at(-1)?.data.candles).toHaveLength(4);
    });
  });
});
