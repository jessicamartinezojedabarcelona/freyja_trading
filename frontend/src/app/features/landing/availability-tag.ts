import { Component, input } from '@angular/core';

import { Availability } from './landing.content';

/** "Disponible" or "Próximamente": nothing on the landing is presented as
 * available before it exists. Symbol and text, never colour alone. */
@Component({
  selector: 'app-availability-tag',
  template: `
    @if (value() === 'now') {
      <span class="chip chip--success"><span aria-hidden="true">✓</span> Disponible</span>
    } @else {
      <span class="chip"><span aria-hidden="true">🔒</span> Próximamente</span>
    }
  `,
})
export class AvailabilityTag {
  readonly value = input.required<Availability>();
}
