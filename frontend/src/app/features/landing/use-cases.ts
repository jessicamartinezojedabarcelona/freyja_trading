import { Component } from '@angular/core';

import { AvailabilityTag } from './availability-tag';
import { USE_CASES } from './landing.content';

@Component({
  selector: 'app-use-cases',
  imports: [AvailabilityTag],
  template: `
    <section class="section" aria-labelledby="use-cases-title">
      <div class="container">
        <header class="section__header">
          <p class="eyebrow">{{ content.eyebrow }}</p>
          <h2 id="use-cases-title" class="heading-section">{{ content.title }}</h2>
        </header>

        <ul class="list">
          @for (item of content.items; track item.title) {
            <li class="row">
              <div class="text">
                <h3 class="heading-card">{{ item.title }}</h3>
                <p>{{ item.text }}</p>
              </div>
              <app-availability-tag [value]="item.availability" />
            </li>
          }
        </ul>
      </div>
    </section>
  `,
  styles: `
    .list {
      margin: 0;
      padding: 0;
      list-style: none;
      border-top: 1px solid var(--freyja-border-subtle);
    }

    .row {
      display: flex;
      flex-direction: column;
      gap: var(--freyja-space-3);
      padding-block: var(--freyja-space-5);
      border-bottom: 1px solid var(--freyja-border-subtle);
      transition: background-color var(--freyja-motion-base);

      @media (min-width: 40rem) {
        flex-direction: row;
        align-items: center;
        justify-content: space-between;
        gap: var(--freyja-space-6);
      }
    }

    .text {
      max-width: 40rem;

      p {
        margin: var(--freyja-space-1) 0 0;
        color: var(--freyja-text-muted);
      }
    }
  `,
})
export class UseCases {
  protected readonly content = USE_CASES;
}
