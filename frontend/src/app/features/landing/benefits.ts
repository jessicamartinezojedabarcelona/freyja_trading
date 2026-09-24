import { Component } from '@angular/core';

import { AvailabilityTag } from './availability-tag';
import { BENEFITS } from './landing.content';

@Component({
  selector: 'app-benefits',
  imports: [AvailabilityTag],
  template: `
    <section class="section band" [id]="content.id" aria-labelledby="benefits-title">
      <div class="container">
        <header class="section__header">
          <p class="eyebrow">{{ content.eyebrow }}</p>
          <h2 id="benefits-title" class="heading-section">{{ content.title }}</h2>
          <p class="lead">{{ content.lead }}</p>
        </header>

        <ul class="grid">
          @for (item of content.items; track item.title) {
            <li class="card card--interactive">
              <app-availability-tag [value]="item.availability" />
              <h3 class="heading-card">{{ item.title }}</h3>
              <p>{{ item.text }}</p>
            </li>
          }
        </ul>
      </div>
    </section>
  `,
  styles: `
    .band {
      background: linear-gradient(
        180deg,
        transparent,
        color-mix(in srgb, var(--freyja-card-bg) 55%, transparent) 20%,
        color-mix(in srgb, var(--freyja-card-bg) 55%, transparent) 80%,
        transparent
      );
    }

    .grid {
      display: grid;
      gap: var(--freyja-space-4);
      margin: 0;
      padding: 0;
      list-style: none;

      @media (min-width: 40rem) {
        grid-template-columns: repeat(2, minmax(0, 1fr));
      }

      @media (min-width: 64rem) {
        grid-template-columns: repeat(3, minmax(0, 1fr));
      }
    }

    .card {
      display: flex;
      flex-direction: column;
      align-items: flex-start;
      gap: var(--freyja-space-3);

      p {
        margin: 0;
        color: var(--freyja-text-muted);
      }
    }
  `,
})
export class Benefits {
  protected readonly content = BENEFITS;
}
