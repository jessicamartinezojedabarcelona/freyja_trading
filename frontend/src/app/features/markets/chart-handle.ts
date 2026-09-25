import { InjectionToken } from '@angular/core';

import { ChartData } from './chart-data';

/** What the page needs from a chart, independent of the drawing library, so the
 * component can be tested without a canvas and the library swapped later. */
export interface ChartHandle {
  /** Replaces the drawn candles. `resetView` fits everything on screen (a new
   * series); otherwise the visible time range is kept (older candles loaded), except that a
   * person who was looking at the newest candle keeps seeing the newest (a refresh). */
  setData(data: ChartData, options: { resetView: boolean }): void;
  destroy(): void;
}

export interface ChartOptions {
  /** IANA zone the time axis and the crosshair are written in (the person's own). */
  timeZone: string;
}

export type ChartFactory = (host: HTMLElement, options: ChartOptions) => Promise<ChartHandle>;

/** The drawing library is loaded on demand, only when a chart is first shown. */
export const CHART_FACTORY = new InjectionToken<ChartFactory>('CHART_FACTORY', {
  providedIn: 'root',
  factory: () => (host: HTMLElement, options: ChartOptions) =>
    import('./lightweight-chart').then((module) => module.createLightweightChart(host, options)),
});
