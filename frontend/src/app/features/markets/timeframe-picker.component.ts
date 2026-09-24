import { Component, computed, input, output } from '@angular/core';

import { PERIOD_GROUPS, PeriodGroup, PeriodOption } from './periods';

/** Candle period selector. Periods the catalog does not enable stay visible but
 * disabled, with the reason, instead of being hidden (UX-DESIGN-SYSTEM-001 §15). */
@Component({
  selector: 'app-timeframe-picker',
  templateUrl: './timeframe-picker.component.html',
  styleUrl: './timeframe-picker.component.scss',
})
export class TimeframePickerComponent {
  readonly options = input.required<readonly PeriodOption[]>();
  readonly selected = input<string | null>(null);
  readonly chosen = output<string>();

  protected readonly groups = computed(() =>
    PERIOD_GROUPS.map((group: PeriodGroup) => ({
      name: group,
      options: this.options().filter((option) => option.group === group),
    })).filter((group) => group.options.length > 0),
  );
}
