import { HttpErrorResponse } from '@angular/common/http';
import { Component, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { ActivatedRoute, NavigationEnd, Router, RouterLink } from '@angular/router';
import {
  BehaviorSubject,
  Observable,
  combineLatest,
  distinctUntilChanged,
  filter,
  forkJoin,
  map,
  of,
  startWith,
  switchMap,
  tap,
} from 'rxjs';
import { catchError } from 'rxjs/operators';

import { InstrumentMappingsOut, InstrumentOut } from '../../core/catalog/catalog.models';
import { CatalogService } from '../../core/catalog/catalog.service';
import { compareDecimals } from '../../core/market-data/decimal';
import { CandleOut, CandleSeriesOut } from '../../core/market-data/market-data.models';
import { MarketDataService } from '../../core/market-data/market-data.service';
import { humanizeUnexpectedError } from '../../shared/http-error-message';
import { formatUtc, toChartData } from './chart-data';
import { CandleChartComponent } from './candle-chart.component';
import { buildPeriodOptions, periodLabel, pickTimeframe } from './periods';
import { SeriesStatusComponent } from './series-status.component';
import { TimeframePickerComponent } from './timeframe-picker.component';

/** Candles requested per page: 500 x 1m is about 8 hours. */
export const PAGE_SIZE = 500;
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

type SeriesState = 'idle' | 'loading' | 'ready' | 'error' | 'no-source';
type OlderState = 'idle' | 'loading' | 'exhausted' | 'error';

/** Market explorer, phase A: stored history from 1 minute up. The URL is the
 * source of truth (instrument, period, source), so a view can be shared and
 * the back button works. Nothing here fetches from a market-data provider. */
@Component({
  selector: 'app-markets-page',
  imports: [RouterLink, CandleChartComponent, SeriesStatusComponent, TimeframePickerComponent],
  templateUrl: './markets.page.html',
  styleUrl: './markets.page.scss',
})
export class MarketsPage {
  private readonly catalog = inject(CatalogService);
  private readonly marketData = inject(MarketDataService);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly refresh$ = new BehaviorSubject(0);

  // -- instrument list ---------------------------------------------------------
  protected readonly listState = signal<'loading' | 'ready' | 'error'>('loading');
  protected readonly instruments = signal<InstrumentOut[]>([]);
  protected readonly totalInstruments = signal(0);
  protected readonly search = signal('');
  protected readonly marketFilter = signal('');

  protected readonly markets = computed(() => {
    const seen = new Map<string, string>();
    for (const instrument of this.instruments()) {
      seen.set(instrument.market.code, instrument.market.display_name);
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
          instrument.product_type.display_name.toLowerCase().includes(term)),
    );
  });

  // -- selection ---------------------------------------------------------------
  protected readonly selectedId = signal<string | null>(null);
  protected readonly detail = signal<Detail | null>(null);
  protected readonly selectedSource = signal<string | null>(null);
  protected readonly selectedTimeframe = signal<string | null>(null);

  protected readonly sources = computed<SourceOption[]>(() => {
    const mappings = this.detail()?.mappings.data_source_instruments ?? [];
    return mappings
      .filter((m) => m.purpose === 'ANALYSIS' && m.is_active && m.data_source.is_active)
      .map((m) => ({ code: m.data_source.code, name: m.data_source.display_name }));
  });
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

  protected readonly chartData = computed(() => toChartData(this.candles()));
  protected readonly seriesKey = computed(
    () => `${this.selectedId()}|${this.selectedSource()}|${this.selectedTimeframe()}`,
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
      `${formatUtc(first.open_time)} y ${formatUtc(last.close_time)}. ` +
      `Último cierre ${last.close}.`
    );
  });

  protected readonly formatUtc = formatUtc;

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
          if (this.seriesKey() !== `${instrumentId}|${source}|${timeframe}`) return;
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
    this.catalog.getInstruments({ isActive: true, limit: INSTRUMENT_PAGE }).subscribe({
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

    this.selectedId.set(instrumentId);
    this.seriesState.set('loading');
    this.olderState.set('idle');

    const cached = this.detail();
    const detail$: Observable<Detail> =
      cached !== null && cached.instrument.instrument_id === instrumentId
        ? of(cached)
        : forkJoin({
            instrument: this.catalog.getInstrument(instrumentId),
            mappings: this.catalog.getInstrumentMappings(instrumentId),
          }).pipe(tap((loaded) => this.detail.set(loaded)));

    return detail$.pipe(
      switchMap((detail) => {
        const sources = this.sources();
        const source =
          selection.source !== null && sources.some((s) => s.code === selection.source)
            ? selection.source
            : (sources[0]?.code ?? null);
        const timeframe = pickTimeframe(selection.timeframe, detail.instrument.timeframes);
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
              this.series.set(series);
              this.candles.set(series.candles);
              this.seriesState.set('ready');
            }),
            map(() => undefined),
          );
      }),
      catchError((error: unknown) => {
        this.detail.update((current) =>
          current?.instrument.instrument_id === instrumentId ? current : null,
        );
        this.series.set(null);
        this.candles.set([]);
        this.errorMessage.set(this.describe(error));
        this.seriesState.set('error');
        return of(undefined);
      }),
    );
  }

  private describe(error: unknown): string {
    if (error instanceof HttpErrorResponse) {
      if (error.status === 404) return 'No se encontró ese instrumento o esa fuente de datos.';
      if (error.status === 422) return 'La consulta no es válida para esta serie.';
      return humanizeUnexpectedError(error, 'No se pudieron cargar las velas. Inténtalo de nuevo.');
    }
    return 'No se pudieron cargar las velas. Inténtalo de nuevo.';
  }
}
