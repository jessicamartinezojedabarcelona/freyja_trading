import { HttpErrorResponse } from '@angular/common/http';
import { DOCUMENT } from '@angular/common';
import { Component, InjectionToken, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { ActivatedRoute, NavigationEnd, Router } from '@angular/router';
import {
  BehaviorSubject,
  Observable,
  combineLatest,
  distinctUntilChanged,
  filter,
  forkJoin,
  fromEvent,
  interval,
  map,
  of,
  startWith,
  switchMap,
  tap,
} from 'rxjs';
import { catchError } from 'rxjs/operators';

import { InstrumentMappingsOut, InstrumentOut } from '../../core/catalog/catalog.models';
import { marketLabel, productLabel } from '../../core/catalog/catalog-labels';
import { CatalogService } from '../../core/catalog/catalog.service';
import { compareDecimals } from '../../core/market-data/decimal';
import { CandleOut, CandleSeriesOut } from '../../core/market-data/market-data.models';
import { MarketDataService } from '../../core/market-data/market-data.service';
import { USER_TIME_ZONE, formatClock, formatInstant, zoneLabel } from '../../core/time/local-time';
import { humanizeUnexpectedError } from '../../shared/http-error-message';
import { toChartData } from './chart-data';
import { CandleChartComponent } from './candle-chart.component';
import { mergeCandles } from './merge-candles';
import { buildPeriodOptions, periodLabel, pickTimeframe } from './periods';
import { SeriesStatusComponent } from './series-status.component';
import { TimeframePickerComponent } from './timeframe-picker.component';

/** Candles requested per page: 500 x 1m is about 8 hours. */
export const PAGE_SIZE = 500;
/** How often the series on screen is refreshed by itself. A frontend setting: the backend
 * already keeps the stored candles current (about every minute). */
export const MARKETS_REFRESH_MS = new InjectionToken<number>('MARKETS_REFRESH_MS', {
  providedIn: 'root',
  factory: () => 30_000,
});
const TABLE_ROWS = 20;
const INSTRUMENT_PAGE = 200;

interface Detail {
  instrument: InstrumentOut;
  mappings: InstrumentMappingsOut;
}

interface SourceOption {
  code: string;
  name: string;
}

interface Selection {
  instrumentId: string | null;
  timeframe: string | null;
  source: string | null;
}

/** Where a series is read from: only ACTIVE analysis mappings of ACTIVE sources. */
function sourcesOf(detail: Detail | null): SourceOption[] {
  const mappings = detail?.mappings.data_source_instruments ?? [];
  return mappings
    .filter((m) => m.purpose === 'ANALYSIS' && m.is_active && m.data_source.is_active)
    .map((m) => ({ code: m.data_source.code, name: m.data_source.display_name }));
}

const keyOf = (instrumentId: string | null, source: string | null, timeframe: string | null) =>
  `${instrumentId}|${source}|${timeframe}`;

/** A response that is not the series that was asked for is never drawn: mixing two
 * series is worse than showing an error. */
class SeriesMismatchError extends Error {}

function assertIsSeries(
  series: CandleSeriesOut,
  wanted: { instrumentId: string; source: string; timeframe: string },
): void {
  if (
    series.instrument_id !== wanted.instrumentId ||
    series.data_source_code !== wanted.source ||
    series.timeframe_code !== wanted.timeframe
  ) {
    throw new SeriesMismatchError('The response is for a different series than requested.');
  }
}

type SeriesState = 'idle' | 'loading' | 'ready' | 'error' | 'no-source';
type OlderState = 'idle' | 'loading' | 'exhausted' | 'error';

/** Market explorer, phase A: stored history from 1 minute up. The URL is the
 * source of truth (instrument, period, source), so a view can be shared and
 * the back button works. Nothing here fetches from a market-data provider. */
@Component({
  selector: 'app-markets-page',
  imports: [CandleChartComponent, SeriesStatusComponent, TimeframePickerComponent],
  templateUrl: './markets.page.html',
  styleUrl: './markets.page.scss',
})
export class MarketsPage {
  private readonly catalog = inject(CatalogService);
  private readonly marketData = inject(MarketDataService);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly refresh$ = new BehaviorSubject(0);
  private readonly document = inject(DOCUMENT);
  private readonly refreshMs = inject(MARKETS_REFRESH_MS);
  private readonly zone = inject(USER_TIME_ZONE);

  // -- time: shown in the person's zone, always saying which -------------------------
  protected readonly zoneText = zoneLabel(this.zone, new Date());
  protected readonly formatTime = (iso: string | null): string => formatInstant(iso, this.zone);
  protected readonly refreshSeconds = Math.round(this.refreshMs / 1000);
  /** When the series on screen last arrived (this browser's clock). */
  protected readonly lastUpdatedAt = signal<Date | null>(null);
  protected readonly lastUpdatedClock = computed(() => {
    const at = this.lastUpdatedAt();
    return at === null ? null : formatClock(at, this.zone);
  });

  // -- instrument list ---------------------------------------------------------
  protected readonly listState = signal<'loading' | 'ready' | 'error'>('loading');
  protected readonly instruments = signal<InstrumentOut[]>([]);
  protected readonly totalInstruments = signal(0);
  protected readonly search = signal('');
  protected readonly marketFilter = signal('');

  protected readonly markets = computed(() => {
    const seen = new Map<string, string>();
    for (const instrument of this.instruments()) {
      seen.set(instrument.market.code, marketLabel(instrument.market));
    }
    return [...seen].map(([code, name]) => ({ code, name }));
  });

  protected readonly visibleInstruments = computed(() => {
    const term = this.search().trim().toLowerCase();
    const market = this.marketFilter();
    return this.instruments().filter(
      (instrument) =>
        (market === '' || instrument.market.code === market) &&
        (term === '' ||
          instrument.canonical_symbol.toLowerCase().includes(term) ||
          instrument.market.display_name.toLowerCase().includes(term) ||
          marketLabel(instrument.market).toLowerCase().includes(term) ||
          instrument.product_type.display_name.toLowerCase().includes(term) ||
          productLabel(instrument.product_type).toLowerCase().includes(term)),
    );
  });

  /** The visible instruments grouped under their market, in catalog order. */
  protected readonly instrumentGroups = computed(() => {
    const groups = new Map<string, { code: string; name: string; items: InstrumentOut[] }>();
    for (const instrument of this.visibleInstruments()) {
      const code = instrument.market.code;
      const group = groups.get(code) ?? { code, name: marketLabel(instrument.market), items: [] };
      group.items.push(instrument);
      groups.set(code, group);
    }
    return [...groups.values()];
  });

  // -- selection ---------------------------------------------------------------
  protected readonly selectedId = signal<string | null>(null);
  protected readonly detail = signal<Detail | null>(null);
  protected readonly selectedSource = signal<string | null>(null);
  protected readonly selectedTimeframe = signal<string | null>(null);

  protected readonly sources = computed<SourceOption[]>(() => sourcesOf(this.detail()));
  protected readonly sourceName = computed(
    () => this.sources().find((s) => s.code === this.selectedSource())?.name ?? '',
  );
  protected readonly periodOptions = computed(() =>
    buildPeriodOptions(this.detail()?.instrument.timeframes ?? []),
  );
  protected readonly timeframeLabel = computed(() => periodLabel(this.selectedTimeframe() ?? ''));

  // -- series ------------------------------------------------------------------
  protected readonly seriesState = signal<SeriesState>('idle');
  protected readonly series = signal<CandleSeriesOut | null>(null);
  protected readonly candles = signal<CandleOut[]>([]);
  protected readonly olderState = signal<OlderState>('idle');
  protected readonly errorMessage = signal('');
  /** True while the same series is being refreshed with its data still on screen. */
  protected readonly refreshing = signal(false);
  /** Set when a refresh failed: the data stays visible, marked as possibly outdated. */
  protected readonly refreshFailure = signal<{ message: string; offline: boolean } | null>(null);
  /** How many candles the first page returned; fewer than a full page is ALL there is. */
  protected readonly storedCount = signal(0);
  protected readonly shortHistory = computed(
    () => this.storedCount() > 0 && this.storedCount() < PAGE_SIZE,
  );

  protected readonly chartData = computed(() => toChartData(this.candles()));
  protected readonly seriesKey = computed(() =>
    keyOf(this.selectedId(), this.selectedSource(), this.selectedTimeframe()),
  );
  protected readonly tableRows = computed(() => [...this.candles()].slice(-TABLE_ROWS).reverse());

  /** Last close and whether it rose or fell against the previous candle, decided
   * on the exact decimal strings (never on floats). */
  protected readonly lastClose = computed(() => {
    const candles = this.candles();
    const last = candles.at(-1);
    if (last === undefined) return null;
    const previous = candles.at(-2);
    const order = previous === undefined ? 0 : compareDecimals(last.close, previous.close);
    return {
      value: last.close,
      arrow: order > 0 ? '▲' : order < 0 ? '▼' : '=',
      text:
        order > 0
          ? 'sube respecto a la vela anterior'
          : order < 0
            ? 'baja respecto a la vela anterior'
            : 'sin cambio respecto a la vela anterior',
      tone: order > 0 ? 'up' : order < 0 ? 'down' : 'flat',
    };
  });

  protected readonly chartLabel = computed(() => {
    const instrument = this.detail()?.instrument;
    const candles = this.candles();
    const first = candles.at(0);
    const last = candles.at(-1);
    if (instrument === undefined || first === undefined || last === undefined) return '';
    return (
      `Gráfico de velas de ${instrument.canonical_symbol}, periodo ${this.timeframeLabel()}, ` +
      `fuente ${this.sourceName()}: ${candles.length} velas cerradas entre ` +
      `${this.formatTime(first.open_time)} y ${this.formatTime(last.close_time)}. ` +
      `Último cierre ${last.close}.`
    );
  });

  constructor() {
    this.loadInstruments();

    // One selection per finished navigation: route params and query params change
    // in the same navigation but are emitted separately, which would otherwise
    // load the same series twice (once with a half-updated selection).
    const navigated$ = this.router.events.pipe(
      filter((event) => event instanceof NavigationEnd),
      startWith(null),
    );
    combineLatest([navigated$, this.refresh$])
      .pipe(
        map(([, tick]): [Selection, number] => [this.currentSelection(), tick]),
        distinctUntilChanged(
          ([a, tickA], [b, tickB]) =>
            tickA === tickB &&
            a.instrumentId === b.instrumentId &&
            a.timeframe === b.timeframe &&
            a.source === b.source,
        ),
        switchMap(([selection]) => this.load(selection)),
        takeUntilDestroyed(),
      )
      .subscribe();

    // Keeps the series current by itself: every `refreshMs`, and at once when a tab that was
    // hidden longer than that becomes visible again (browsers slow timers in the background).
    interval(this.refreshMs)
      .pipe(takeUntilDestroyed())
      .subscribe(() => this.autoRefresh());
    fromEvent(this.document, 'visibilitychange')
      .pipe(
        filter(() => this.isStale()),
        takeUntilDestroyed(),
      )
      .subscribe(() => this.autoRefresh());
  }

  protected marketName(instrument: InstrumentOut): string {
    return marketLabel(instrument.market);
  }

  protected productName(instrument: InstrumentOut): string {
    return productLabel(instrument.product_type);
  }

  // -- user actions ------------------------------------------------------------
  protected chooseInstrument(instrumentId: string): void {
    // The period is kept; the source is specific to an instrument, so it is not.
    void this.router.navigate(['/mercados', instrumentId], {
      queryParams: { source: null },
      queryParamsHandling: 'merge',
    });
  }

  protected chooseTimeframe(code: string): void {
    void this.router.navigate([], {
      relativeTo: this.route,
      queryParams: { tf: code },
      queryParamsHandling: 'merge',
    });
  }

  protected chooseSource(code: string): void {
    void this.router.navigate([], {
      relativeTo: this.route,
      queryParams: { source: code },
      queryParamsHandling: 'merge',
    });
  }

  protected reload(): void {
    this.refresh$.next(this.refresh$.value + 1);
  }

  /** Only while someone can see it, the series is loaded, and nothing else is loading: it
   * never stacks requests, never hides an error, never wastes a hidden tab's requests. */
  private autoRefresh(): void {
    if (
      this.document.visibilityState !== 'visible' ||
      this.seriesState() !== 'ready' ||
      this.refreshing() ||
      this.olderState() === 'loading'
    ) {
      return;
    }
    this.reload();
  }

  private isStale(): boolean {
    const at = this.lastUpdatedAt();
    return at === null || Date.now() - at.getTime() >= this.refreshMs;
  }

  protected loadOlder(): void {
    const instrumentId = this.selectedId();
    const source = this.selectedSource();
    const timeframe = this.selectedTimeframe();
    const oldest = this.candles().at(0);
    if (
      instrumentId === null ||
      source === null ||
      timeframe === null ||
      oldest === undefined ||
      this.olderState() === 'loading'
    ) {
      return;
    }
    this.olderState.set('loading');
    this.marketData
      .getCandles({
        instrumentId,
        dataSourceCode: source,
        timeframeCode: timeframe,
        end: oldest.open_time,
        limit: PAGE_SIZE,
      })
      .subscribe({
        next: (older) => {
          if (this.seriesKey() !== keyOf(instrumentId, source, timeframe)) return;
          try {
            assertIsSeries(older, { instrumentId, source, timeframe });
          } catch {
            this.olderState.set('error');
            return;
          }
          this.candles.update((current) => [...older.candles, ...current]);
          this.olderState.set(older.candles.length < PAGE_SIZE ? 'exhausted' : 'idle');
        },
        error: () => this.olderState.set('error'),
      });
  }

  protected onSearch(value: string): void {
    this.search.set(value);
  }

  protected onMarketFilter(value: string): void {
    this.marketFilter.set(value);
  }

  // -- loading -----------------------------------------------------------------
  private currentSelection(): Selection {
    const snapshot = this.route.snapshot;
    return {
      instrumentId: snapshot.paramMap.get('instrumentId'),
      timeframe: snapshot.queryParamMap.get('tf'),
      source: snapshot.queryParamMap.get('source'),
    };
  }

  private loadInstruments(): void {
    // Only what can actually be shown: instruments an active source publishes candles for.
    this.catalog
      .getInstruments({ isActive: true, hasMarketData: true, limit: INSTRUMENT_PAGE })
      .subscribe({
        next: (page) => {
          this.instruments.set(page.items);
          this.totalInstruments.set(page.total);
          this.listState.set('ready');
        },
        error: () => this.listState.set('error'),
      });
  }

  private resetSeries(state: SeriesState): void {
    this.seriesState.set(state);
    this.series.set(null);
    this.candles.set([]);
    this.olderState.set('idle');
    this.refreshing.set(false);
    this.refreshFailure.set(null);
    this.storedCount.set(0);
  }

  private resolve(detail: Detail, selection: Selection) {
    const sources = sourcesOf(detail);
    const source =
      selection.source !== null && sources.some((s) => s.code === selection.source)
        ? selection.source
        : (sources[0]?.code ?? null);
    const timeframe = pickTimeframe(selection.timeframe, detail.instrument.timeframes);
    return { source, timeframe };
  }

  private load(selection: Selection): Observable<void> {
    const instrumentId = selection.instrumentId;
    if (instrumentId === null) {
      this.selectedId.set(null);
      this.detail.set(null);
      this.selectedSource.set(null);
      this.selectedTimeframe.set(null);
      this.resetSeries('idle');
      return of(undefined);
    }

    // Read before anything changes: is this a refresh of the series already on screen?
    const shownKey = this.seriesKey();
    const hadData = this.series() !== null;
    const cached = this.detail();
    const known = cached !== null && cached.instrument.instrument_id === instrumentId;
    const resolved = known ? this.resolve(cached, selection) : null;
    const isRefresh =
      hadData &&
      resolved !== null &&
      keyOf(instrumentId, resolved.source, resolved.timeframe) === shownKey;

    this.selectedId.set(instrumentId);
    this.refreshFailure.set(null);
    if (isRefresh) {
      // Same series: keep the chart, its data and the older pages the person loaded; show
      // progress next to it.
      this.refreshing.set(true);
    } else {
      // Another series: never leave the previous one visible.
      this.olderState.set('idle');
      this.refreshing.set(false);
      this.seriesState.set('loading');
    }

    const detail$: Observable<Detail> = known
      ? of(cached)
      : forkJoin({
          instrument: this.catalog.getInstrument(instrumentId),
          mappings: this.catalog.getInstrumentMappings(instrumentId),
        }).pipe(tap((loaded) => this.detail.set(loaded)));

    return detail$.pipe(
      switchMap((detail) => {
        const { source, timeframe } = this.resolve(detail, selection);
        this.selectedSource.set(source);
        this.selectedTimeframe.set(timeframe);

        if (source === null || timeframe === null) {
          this.resetSeries('no-source');
          return of(undefined);
        }
        return this.marketData
          .getCandles({
            instrumentId,
            dataSourceCode: source,
            timeframeCode: timeframe,
            limit: PAGE_SIZE,
          })
          .pipe(
            tap((series) => {
              assertIsSeries(series, { instrumentId, source, timeframe });
              this.series.set(series);
              if (isRefresh) {
                // The newest page joins what is on screen; older pages already loaded stay.
                this.candles.update((current) => mergeCandles(current, series.candles));
              } else {
                this.candles.set(series.candles);
                this.storedCount.set(series.candles.length);
                // Fewer than a full page means the whole stored history came back.
                this.olderState.set(series.candles.length < PAGE_SIZE ? 'exhausted' : 'idle');
              }
              this.lastUpdatedAt.set(new Date());
              this.refreshing.set(false);
              this.seriesState.set('ready');
            }),
            map(() => undefined),
          );
      }),
      catchError((error: unknown) => {
        this.refreshing.set(false);
        if (isRefresh && this.series() !== null) {
          // The refresh failed, not the data on screen: keep it, marked as possibly
          // outdated, instead of wiping the chart (design system §14.13).
          this.refreshFailure.set({
            message: this.describe(error),
            offline: error instanceof HttpErrorResponse && error.status === 0,
          });
          return of(undefined);
        }
        this.detail.update((current) =>
          current?.instrument.instrument_id === instrumentId ? current : null,
        );
        this.series.set(null);
        this.candles.set([]);
        this.storedCount.set(0);
        this.errorMessage.set(this.describe(error));
        this.seriesState.set('error');
        return of(undefined);
      }),
    );
  }

  private describe(error: unknown): string {
    if (error instanceof SeriesMismatchError) {
      return 'La respuesta del servidor no corresponde a la serie pedida y se descartó.';
    }
    if (error instanceof HttpErrorResponse) {
      if (error.status === 404) return 'No se encontró ese instrumento o esa fuente de datos.';
      if (error.status === 422) return 'La consulta no es válida para esta serie.';
      return humanizeUnexpectedError(error, 'No se pudieron cargar las velas. Inténtalo de nuevo.');
    }
    return 'No se pudieron cargar las velas. Inténtalo de nuevo.';
  }
}
