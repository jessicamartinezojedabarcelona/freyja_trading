import {
  Component,
  DestroyRef,
  ElementRef,
  afterNextRender,
  effect,
  inject,
  input,
  signal,
  untracked,
  viewChild,
} from '@angular/core';

import { USER_TIME_ZONE } from '../../core/time/local-time';
import { ChartData } from './chart-data';
import { CHART_FACTORY, ChartHandle } from './chart-handle';

/** Draws candles. It only draws: quality, freshness and the textual alternative
 * live next to it, and it never invents or smooths data. */
@Component({
  selector: 'app-candle-chart',
  template: `
    <div
      #host
      class="chart"
      role="img"
      [attr.aria-label]="label()"
      [class.chart--hidden]="failed()"
    ></div>
    @if (failed()) {
      <p class="chart-error" role="alert">
        ⚠ No se pudo cargar el gráfico. Los datos siguen disponibles en la tabla de velas.
      </p>
    }
  `,
  styles: `
    :host {
      display: block;
    }
    .chart {
      width: 100%;
      height: 26rem;
    }
    .chart--hidden {
      display: none;
    }
    .chart-error {
      margin: 0;
      padding: 1rem;
      color: var(--freyja-text-cream);
      border: 1px solid var(--freyja-status-error);
    }
  `,
})
export class CandleChartComponent {
  readonly data = input.required<ChartData>();
  /** Accessible name; summarises what the chart shows. */
  readonly label = input.required<string>();
  /** Identifies the series (instrument, source, period). A change re-fits the
   * view; the same key with more candles (older ones loaded) keeps it. */
  readonly seriesKey = input.required<string>();

  protected readonly failed = signal(false);

  private readonly host = viewChild.required<ElementRef<HTMLElement>>('host');
  private handle: ChartHandle | null = null;
  private drawnKey: string | null = null;
  private destroyed = false;

  constructor() {
    const factory = inject(CHART_FACTORY);
    const timeZone = inject(USER_TIME_ZONE);
    const destroyRef = inject(DestroyRef);

    afterNextRender(() => {
      factory(this.host().nativeElement, { timeZone })
        .then((handle) => {
          if (this.destroyed) {
            handle.destroy();
            return;
          }
          this.handle = handle;
          this.draw();
        })
        .catch(() => this.failed.set(true));
    });

    effect(() => {
      this.data();
      this.seriesKey();
      untracked(() => this.draw());
    });

    destroyRef.onDestroy(() => {
      this.destroyed = true;
      this.handle?.destroy();
      this.handle = null;
    });
  }

  private draw(): void {
    if (this.handle === null) return;
    const key = this.seriesKey();
    this.handle.setData(this.data(), { resetView: key !== this.drawnKey });
    this.drawnKey = key;
  }
}
