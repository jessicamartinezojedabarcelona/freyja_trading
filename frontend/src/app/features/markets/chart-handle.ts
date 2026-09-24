import { InjectionToken } from '@angular/core';

import { ChartData } from './chart-data';

/** What the page needs from a chart, independent of the drawing library, so the
 * component can be tested without a canvas and the library swapped later. */
export interface ChartHandle {
  /** Replaces the drawn candles. `resetView` fits everything on screen (a new
   * series); otherwise the visible time range is kept (older candles loaded). */
  setData(data: ChartData, options: { resetView: boolean }): void;
  destroy(): void;
}

export type ChartFactory = (host: HTMLElement) => Promise<ChartHandle>;

/** The drawing library is loaded on demand, only when a chart is first shown. */
export const CHART_FACTORY = new InjectionToken<ChartFactory>('CHART_FACTORY', {
  providedIn: 'root',
  factory: () => (host: HTMLElement) =>
    import('./lightweight-chart').then((module) => module.createLightweightChart(host)),
});
