import { Component } from '@angular/core';

import { PRINCIPLES } from './landing.content';

/** Takes the place testimonials would have: Freyja has no customers to quote yet,
 * and invented reviews would be exactly the kind of untruth it stands against. */
@Component({
  selector: 'app-principles',
  template: `
    <section class="section band" aria-labelledby="principles-title">
      <div class="container">
        <header class="section__header">
          <p class="eyebrow">{{ content.eyebrow }}</p>
          <h2 id="principles-title" class="heading-section">{{ content.title }}</h2>
        </header>

        <ul class="grid">
          @for (item of content.items; track item.title) {
            <li class="item">
              <span class="mark" aria-hidden="true">✕</span>
              <div>
                <h3 class="heading-card">{{ item.title }}</h3>
                <p>{{ item.text }}</p>
              </div>
            </li>
          }
        </ul>
      </div>
    </section>
  `,
  styles: `
    .band {
      background: color-mix(in srgb, var(--freyja-card-bg) 55%, transparent);
      border-block: 1px solid var(--freyja-border-subtle);
    }

    .grid {
      display: grid;
      gap: var(--freyja-space-6) var(--freyja-space-7);
      margin: 0;
      padding: 0;
      list-style: none;

      @media (min-width: 48rem) {
        grid-template-columns: repeat(2, minmax(0, 1fr));
      }
    }

    .item {
      display: flex;
      gap: var(--freyja-space-4);

      p {
        margin: var(--freyja-space-2) 0 0;
        color: var(--freyja-text-muted);
      }
    }

    .mark {
      display: grid;
      flex: none;
      width: 2rem;
      height: 2rem;
      place-items: center;
      color: var(--freyja-gold-bright);
      font-size: var(--freyja-text-size-sm);
      border: 1px solid var(--freyja-border);
      border-radius: var(--freyja-radius-full);
    }
  `,
})
export class Principles {
  protected readonly content = PRINCIPLES;
}
