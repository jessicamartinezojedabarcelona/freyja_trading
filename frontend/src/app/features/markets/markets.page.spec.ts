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
import { USER_TIME_ZONE } from '../../core/time/local-time';
import { ChartData } from './chart-data';
import { CHART_FACTORY, ChartHandle } from './chart-handle';
import { MARKETS_REFRESH_MS, MarketsPage, PAGE_SIZE } from './markets.page';

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

  // A fixed zone (never the machine's own) and an interval too long to ever fire by itself:
  // a test that wants the automatic refresh asks for it.
  interface Environment {
    zone?: string;
    refreshMs?: number;
  }

  async function open(url: string, environment: Environment = {}): Promise<void> {
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
        { provide: USER_TIME_ZONE, useValue: environment.zone ?? 'Europe/Madrid' },
        { provide: MARKETS_REFRESH_MS, useValue: environment.refreshMs ?? 3_600_000 },
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
    environment: Environment = {},
  ): Promise<TestRequest> {
    await open(url, environment);
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
      expect(note).toContain('Hora local (Europe/Madrid, GMT+2)');
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
      // 12:00-12:02 UTC is 14:00-14:02 in Madrid: the person's time, with the zone.
      expect(label).toContain('24/09/2026, 14:00:00 GMT+2');
      expect(label).toContain('24/09/2026, 14:03:00 GMT+2');
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
      expect(squash(rows[0].querySelector('th'))).toContain('14:24:00 GMT+2');
      expect(squash(rows[19].querySelector('th'))).toContain('14:05:00 GMT+2');
      expect(squash(details.querySelector('caption'))).toContain('BTC/USDT');
      expect(squash(details.querySelector('caption'))).toContain(
        'hora local: Europe/Madrid, GMT+2',
      );
      const headers = [...details.querySelectorAll('thead th')].map((h) => squash(h));
      expect(headers).toEqual([
        'Abre (hora local)',
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
    // A full page means there may be more stored before it; fewer means that was all.
    const fullPage = () => Array.from({ length: PAGE_SIZE }, (_, i) => makeCandle(i));
    const olderButton = () =>
      [...root().querySelectorAll<HTMLButtonElement>('.chart-actions .btn')].find((b) =>
        squash(b).includes('velas anteriores'),
      )!;

    it('asks for candles before the oldest one shown and keeps the view where it was', async () => {
      await openLoaded(`/mercados/${INSTRUMENT_ID}`, makeSeries({ candles: fullPage() }));
      const oldestOpen = makeCandle(0).open_time;

      olderButton().click();
      const request = candlesRequest();
      expect(request.request.params.get('end')).toBe(oldestOpen);
      expect(request.request.params.get('limit')).toBe(String(PAGE_SIZE));
      expect(request.request.params.get('instrument_id')).toBe(INSTRUMENT_ID);
      request.flush(makeSeries({ candles: [makeCandle(-2), makeCandle(-1)] }));
      await settle();

      const last = chart.drawn.at(-1)!;
      expect(last.data.candles).toHaveLength(PAGE_SIZE + 2);
      const times = last.data.candles.map((c) => c.time);
      expect(times).toEqual([...times].sort((a, b) => a - b));
      expect(last.resetView).toBe(false);
    });

    it('says there is nothing older once a page comes back short', async () => {
      await openLoaded(`/mercados/${INSTRUMENT_ID}`, makeSeries({ candles: fullPage() }));

      olderButton().click();
      candlesRequest().flush(makeSeries({ candles: [makeCandle(-1)] }));
      await settle();

      expect(text()).toContain('No hay velas anteriores guardadas.');
      expect(text()).not.toContain('Cargar velas anteriores');
    });

    it('keeps offering more while full pages keep coming', async () => {
      await openLoaded(`/mercados/${INSTRUMENT_ID}`, makeSeries({ candles: fullPage() }));
      const older = Array.from({ length: PAGE_SIZE }, (_, i) => makeCandle(-PAGE_SIZE + i));

      olderButton().click();
      candlesRequest().flush(makeSeries({ candles: older }));
      await settle();

      expect(text()).toContain('Cargar velas anteriores');
      expect(chart.drawn.at(-1)?.data.candles).toHaveLength(PAGE_SIZE * 2);
    });

    it('reports a failure without losing what is already drawn', async () => {
      await openLoaded(`/mercados/${INSTRUMENT_ID}`, makeSeries({ candles: fullPage() }));

      olderButton().click();
      candlesRequest().flush({}, { status: 500, statusText: 'Server Error' });
      await settle();

      expect(text()).toContain('No se pudieron cargar las velas anteriores.');
      expect(chart.drawn.at(-1)?.data.candles).toHaveLength(PAGE_SIZE);
    });

    it('does not start a second request while one is running', async () => {
      await openLoaded(`/mercados/${INSTRUMENT_ID}`, makeSeries({ candles: fullPage() }));
      const button = olderButton();

      button.click();
      harness.detectChanges();
      expect(button.disabled).toBe(true);
      button.click();
      const pending = httpMock.match((r) => r.url === CANDLES_URL);
      expect(pending).toHaveLength(1);
      pending[0].flush(makeSeries({ candles: [] }));
      await settle();
    });

    it('offers nothing older when the whole stored history fits in the first page', async () => {
      await openLoaded(); // 3 candles: fewer than a page, so that is everything there is

      expect(text()).toContain('No hay velas anteriores guardadas.');
      expect(olderButton()).toBeUndefined();
    });

    it('discards an older page that belongs to a different series', async () => {
      await openLoaded(`/mercados/${INSTRUMENT_ID}`, makeSeries({ candles: fullPage() }));

      olderButton().click();
      candlesRequest().flush(
        makeSeries({ timeframe_code: '5m', candles: [makeCandle(-2), makeCandle(-1)] }),
      );
      await settle();

      expect(chart.drawn.at(-1)?.data.candles).toHaveLength(PAGE_SIZE); // nothing mixed in
      expect(text()).toContain('No se pudieron cargar las velas anteriores.');
    });
  });

  describe('the instrument list', () => {
    it('asks only for instruments that have market data', async () => {
      await open('/mercados');
      const request = httpMock.expectOne((r) => r.url === INSTRUMENTS_URL);
      expect(request.request.params.get('has_market_data')).toBe('true');
      request.flush({ items: [BTC], total: 1, limit: 200, offset: 0 });
      await settle();
    });

    it('says so, instead of blaming the filter, when no instrument has data yet', async () => {
      await open('/mercados');
      flushInstruments([]);
      await settle();

      expect(text()).toContain('Todavía no hay instrumentos con datos de mercado.');
      expect(text()).not.toContain('Ningún instrumento coincide');
    });
  });

  describe('a response for a different series than the one requested', () => {
    it('is never drawn: it would mix two instruments or two periods', async () => {
      await open(`/mercados/${INSTRUMENT_ID}`);
      flushInstruments();
      flushDetail();
      candlesRequest().flush(makeSeries({ instrument_id: OTHER_INSTRUMENT_ID }));
      await settle();

      expect(chart.drawn).toHaveLength(0);
      expect(root().querySelector('[role="alert"]')).not.toBeNull();
    });

    it('is rejected when only the period differs', async () => {
      await open(`/mercados/${INSTRUMENT_ID}`);
      flushInstruments();
      flushDetail();
      candlesRequest().flush(makeSeries({ timeframe_code: '5m' }));
      await settle();

      expect(chart.drawn).toHaveLength(0);
      expect(root().querySelector('[role="alert"]')).not.toBeNull();
    });
  });

  describe('when a refresh fails', () => {
    const refresh = () =>
      [...root().querySelectorAll<HTMLButtonElement>('.chart-actions .btn')]
        .find((b) => squash(b).startsWith('Actualiz'))!
        .click();

    it('keeps the chart and warns that it may be out of date', async () => {
      await openLoaded();

      refresh();
      candlesRequest().flush({}, { status: 500, statusText: 'Server Error' });
      await settle();

      expect(root().querySelector('app-candle-chart')).not.toBeNull();
      expect(chart.destroyed).toBe(0);
      const alert = squash(root().querySelector('section[aria-label="Gráfico de velas"] .alert'));
      expect(alert).toContain('No se pudo actualizar.');
      expect(alert).toContain('pueden estar desactualizados');
      expect(alert).toContain('Última actualización válida:');
    });

    it('says the connection failed when Freyja cannot be reached', async () => {
      await openLoaded();

      refresh();
      candlesRequest().error(new ProgressEvent('error'), { status: 0 });
      await settle();

      expect(text()).toContain('Sin conexión con Freyja.');
      expect(root().querySelector('app-candle-chart')).not.toBeNull();
    });

    it('goes away once a refresh succeeds', async () => {
      await openLoaded();
      refresh();
      candlesRequest().flush({}, { status: 500, statusText: 'Server Error' });
      await settle();
      expect(text()).toContain('No se pudo actualizar.');

      refresh();
      candlesRequest().flush(makeSeries());
      await settle();

      expect(text()).not.toContain('No se pudo actualizar.');
    });

    it('does not keep the old chart when the failure is for a different selection', async () => {
      await openLoaded();

      // Changing the period is not a refresh: the old candles would be the wrong ones.
      await harness.navigateByUrl(`/mercados/${INSTRUMENT_ID}?tf=5m`);
      candlesRequest().flush({}, { status: 500, statusText: 'Server Error' });
      await settle();

      expect(root().querySelector('app-candle-chart')).toBeNull();
      expect(root().querySelector('[role="alert"]')).not.toBeNull();
    });

    it('disables the button while the refresh is running', async () => {
      await openLoaded();
      refresh();
      harness.detectChanges();

      const button = [...root().querySelectorAll<HTMLButtonElement>('.chart-actions .btn')].find(
        (b) => squash(b) === 'Actualizando…',
      )!;
      expect(button.disabled).toBe(true);

      candlesRequest().flush(makeSeries());
      await settle();
    });
  });

  describe('when only a little history is stored', () => {
    it('warns that it may not be enough to analyse', async () => {
      await openLoaded(); // 3 candles

      expect(text()).toContain('Solo hay 3 velas guardadas para esta serie');
    });

    it('stays quiet once a full page is stored', async () => {
      await openLoaded(
        `/mercados/${INSTRUMENT_ID}`,
        makeSeries({ candles: Array.from({ length: PAGE_SIZE }, (_, i) => makeCandle(i)) }),
      );

      expect(text()).not.toContain('velas guardadas para esta serie');
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

  describe('the time shown to the person', () => {
    it('is their own zone, in the chart note, the status and the table', async () => {
      await openLoaded(`/mercados/${INSTRUMENT_ID}`, makeSeries(), { zone: 'America/Bogota' });

      const content = text();
      expect(content).toContain('Hora local (America/Bogota, GMT-5)');
      expect(content).toContain('07:02:00 GMT-5'); // the last candle opens at 12:02 UTC
      expect(content).not.toContain(' UTC');
    });

    it('says UTC when that is really the zone', async () => {
      await openLoaded(`/mercados/${INSTRUMENT_ID}`, makeSeries(), { zone: 'UTC' });

      expect(text()).toContain('Hora local (UTC)');
      expect(text()).toContain('12:02:00 UTC');
    });

    it('asks the API in UTC whatever the zone of the person is', async () => {
      await open(`/mercados/${INSTRUMENT_ID}`, { zone: 'Asia/Tokyo' });
      flushInstruments();
      flushDetail();
      candlesRequest().flush(
        makeSeries({ candles: Array.from({ length: PAGE_SIZE }, (_, i) => makeCandle(i)) }),
      );
      await settle();

      [...root().querySelectorAll<HTMLButtonElement>('.chart-actions .btn')]
        .find((b) => squash(b).includes('velas anteriores'))!
        .click();
      const request = candlesRequest();
      expect(request.request.params.get('end')).toBe(makeCandle(0).open_time);
      expect(request.request.params.get('end')).toMatch(/Z$/); // an instant in UTC, not local text
      request.flush(makeSeries({ candles: [makeCandle(-1)] }));
      await settle();
    });
  });

  describe('keeping itself current', () => {
    const refreshMs = 30_000;
    const environment: Environment = { refreshMs };

    beforeEach(() => {
      // Only the interval and the clock are faked: promises and timeouts stay real.
      vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval', 'Date'] });
      vi.setSystemTime(new Date('2026-09-25T17:45:12Z'));
    });

    afterEach(() => {
      vi.useRealTimers();
    });

    const advance = (ms: number) => vi.advanceTimersByTime(ms);
    const older = () =>
      [...root().querySelectorAll<HTMLButtonElement>('.chart-actions .btn')].find((b) =>
        squash(b).includes('velas anteriores'),
      );

    it('asks for the newest candles every 30 seconds without a reload of the page', async () => {
      await openLoaded(`/mercados/${INSTRUMENT_ID}`, makeSeries(), environment);
      expect(chart.drawn.at(-1)?.data.candles).toHaveLength(3);

      advance(refreshMs);
      const request = candlesRequest();
      expect(request.request.params.get('limit')).toBe(String(PAGE_SIZE));
      request.flush(
        makeSeries({ candles: [makeCandle(0), makeCandle(1), makeCandle(2), makeCandle(3)] }),
      );
      await settle();

      expect(chart.drawn.at(-1)?.data.candles).toHaveLength(4);
      expect(chartsCreated).toBe(1); // the same chart, not a new page
    });

    it('does nothing before the interval has passed', async () => {
      await openLoaded(`/mercados/${INSTRUMENT_ID}`, makeSeries(), environment);

      advance(refreshMs - 1);
      httpMock.expectNone((r) => r.url === CANDLES_URL);
    });

    it('keeps refreshing on every interval', async () => {
      await openLoaded(`/mercados/${INSTRUMENT_ID}`, makeSeries(), environment);

      for (let i = 0; i < 3; i++) {
        advance(refreshMs);
        candlesRequest().flush(makeSeries());
        await settle();
      }
      expect(chart.drawn.length).toBeGreaterThanOrEqual(4);
    });

    it('shows a spinner while it refreshes and says when it was last updated, in local time', async () => {
      await openLoaded(`/mercados/${INSTRUMENT_ID}`, makeSeries(), environment);
      // Loaded at 17:45:12 UTC = 19:45:12 in Madrid.
      expect(text()).toContain('Actualizado a las 19:45:12 · se actualiza sola cada 30 s');
      expect(root().querySelector('.spinner')).toBeNull();

      advance(refreshMs);
      harness.detectChanges();
      expect(root().querySelector('.live .spinner')).not.toBeNull();
      expect(squash(root().querySelector('.live'))).toContain('Actualizando…');

      candlesRequest().flush(makeSeries());
      await settle();

      expect(root().querySelector('.spinner')).toBeNull();
      expect(text()).toContain('Actualizado a las 19:45:42'); // 30 s later on the same clock
    });

    it('never stacks requests: a refresh in progress is not asked again', async () => {
      await openLoaded(`/mercados/${INSTRUMENT_ID}`, makeSeries(), environment);

      advance(refreshMs);
      const first = candlesRequest();
      advance(refreshMs); // the answer has not come back yet
      httpMock.expectNone((r) => r.url === CANDLES_URL);

      first.flush(makeSeries());
      await settle();
    });

    it('does not ask while the tab is hidden', async () => {
      await openLoaded(`/mercados/${INSTRUMENT_ID}`, makeSeries(), environment);
      const hidden = vi.spyOn(document, 'visibilityState', 'get').mockReturnValue('hidden');

      advance(refreshMs * 3);
      httpMock.expectNone((r) => r.url === CANDLES_URL);

      hidden.mockRestore();
    });

    it('refreshes at once when a tab hidden for longer than the interval comes back', async () => {
      await openLoaded(`/mercados/${INSTRUMENT_ID}`, makeSeries(), environment);
      const state = vi.spyOn(document, 'visibilityState', 'get').mockReturnValue('hidden');
      advance(refreshMs * 3);
      httpMock.expectNone((r) => r.url === CANDLES_URL);

      state.mockReturnValue('visible');
      document.dispatchEvent(new Event('visibilitychange'));
      candlesRequest().flush(makeSeries());
      await settle();

      state.mockRestore();
    });

    it('does not refresh again when the tab comes back before the interval is up', async () => {
      await openLoaded(`/mercados/${INSTRUMENT_ID}`, makeSeries(), environment);

      advance(5_000);
      document.dispatchEvent(new Event('visibilitychange'));
      httpMock.expectNone((r) => r.url === CANDLES_URL);
    });

    it('does not refresh a series that failed to load: that is for the retry button', async () => {
      await open(`/mercados/${INSTRUMENT_ID}`, environment);
      flushInstruments();
      flushDetail();
      candlesRequest().flush({}, { status: 500, statusText: 'Server Error' });
      await settle();

      advance(refreshMs * 2);
      httpMock.expectNone((r) => r.url === CANDLES_URL);
    });

    it('does not refresh while nothing is chosen', async () => {
      await open('/mercados', environment);
      flushInstruments();
      await settle();

      advance(refreshMs * 2);
      httpMock.expectNone((r) => r.url === CANDLES_URL);
    });

    it('keeps the chart and warns, without erasing anything, when a refresh fails', async () => {
      await openLoaded(`/mercados/${INSTRUMENT_ID}`, makeSeries(), environment);

      advance(refreshMs);
      candlesRequest().flush({}, { status: 500, statusText: 'Server Error' });
      await settle();

      expect(root().querySelector('app-candle-chart')).not.toBeNull();
      expect(chart.destroyed).toBe(0);
      expect(text()).toContain('No se pudo actualizar.');
      expect(chart.drawn.at(-1)?.data.candles).toHaveLength(3);
    });

    it('keeps the older candles that were loaded, and does not move the view', async () => {
      const full = Array.from({ length: PAGE_SIZE }, (_, i) => makeCandle(i));
      await openLoaded(`/mercados/${INSTRUMENT_ID}`, makeSeries({ candles: full }), environment);
      older()!.click();
      candlesRequest().flush(makeSeries({ candles: [makeCandle(-2), makeCandle(-1)] }));
      await settle();
      expect(chart.drawn.at(-1)?.data.candles).toHaveLength(PAGE_SIZE + 2);

      // The newest page comes back with one more candle, the older ones not in it.
      advance(refreshMs);
      candlesRequest().flush(makeSeries({ candles: [...full.slice(1), makeCandle(PAGE_SIZE)] }));
      await settle();

      const drawn = chart.drawn.at(-1)!;
      expect(drawn.data.candles).toHaveLength(PAGE_SIZE + 3); // two older + 500 + the new one
      expect(drawn.resetView).toBe(false);
      expect(drawn.data.candles[0].time).toBe(Date.parse(makeCandle(-2).open_time) / 1000);
    });

    it('does not turn "nothing older" back into "maybe more" on a refresh', async () => {
      await openLoaded(`/mercados/${INSTRUMENT_ID}`, makeSeries(), environment); // 3 candles: all there is
      expect(text()).toContain('No hay velas anteriores guardadas.');

      advance(refreshMs);
      candlesRequest().flush(makeSeries());
      await settle();

      expect(text()).toContain('No hay velas anteriores guardadas.');
    });
  });
});
