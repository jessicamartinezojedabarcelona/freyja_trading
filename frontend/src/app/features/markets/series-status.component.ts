import { Component, computed, inject, input } from '@angular/core';

import { CandleSeriesOut } from '../../core/market-data/market-data.models';
import { USER_TIME_ZONE, formatInstant, zoneLabel } from '../../core/time/local-time';
import { formatAge } from './chart-data';
import {
  FRESHNESS_PRESENTATION,
  PROVIDER_PRESENTATION,
  QUALITY_PRESENTATION,
  issueLabel,
} from './quality-labels';

/** Everything a person needs to judge how far to trust a series: where it comes
 * from, how current it is, what is wrong with it, and how the last refresh went.
 * A series that is not OK is announced first and plainly. */
@Component({
  selector: 'app-series-status',
  templateUrl: './series-status.component.html',
  styleUrl: './series-status.component.scss',
})
export class SeriesStatusComponent {
  readonly series = input.required<CandleSeriesOut>();
  /** Human name of the source (e.g. "Binance"). */
  readonly sourceName = input.required<string>();

  private readonly zone = inject(USER_TIME_ZONE);
  /** Where every time on this card is: said once, so the times themselves stay plain. */
  protected readonly zoneText = zoneLabel(this.zone, new Date());
  /** Every time is shown in the person's own zone, with the zone written next to it. */
  protected readonly formatTime = (iso: string | null): string => formatInstant(iso, this.zone);
  protected readonly issueLabel = issueLabel;
  protected readonly quality = computed(() => QUALITY_PRESENTATION[this.series().quality]);
  protected readonly freshness = computed(
    () => FRESHNESS_PRESENTATION[this.series().freshness.status],
  );
  protected readonly providerStatus = computed(() => {
    const provider = this.series().provider;
    return provider === null ? null : PROVIDER_PRESENTATION[provider.last_status];
  });
  /** How long ago the newest stored candle closed, as of the moment of checking. */
  protected readonly age = computed(() => {
    const { latest_close_time: closed, checked_at: checked } = this.series().freshness;
    if (closed === null) return null;
    return formatAge((Date.parse(checked) - Date.parse(closed)) / 1000);
  });
}
