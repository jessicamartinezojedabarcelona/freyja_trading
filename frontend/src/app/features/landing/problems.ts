import { Component } from '@angular/core';

import { PROBLEMS } from './landing.content';

@Component({
  selector: 'app-problems',
  template: `
    <section class="section" aria-labelledby="problems-title">
      <div class="container">
        <header class="section__header">
          <p class="eyebrow">{{ content.eyebrow }}</p>
          <h2 id="problems-title" class="heading-section">{{ content.title }}</h2>
          <p class="lead">{{ content.lead }}</p>
        </header>

        <ul class="grid">
          @for (item of content.items; track item.title; let index = $index) {
            <li class="card card--interactive">
              <span class="number" aria-hidden="true">{{ '0' + (index + 1) }}</span>
              <h3 class="heading-card">{{ item.title }}</h3>
              <p>{{ item.text }}</p>
            </li>
          }
        </ul>
      </div>
    </section>
  `,
  styles: `
    .grid {
      display: grid;
      gap: var(--freyja-space-4);
      margin: 0;
      padding: 0;
      list-style: none;

      @media (min-width: 40rem) {
        grid-template-columns: repeat(2, minmax(0, 1fr));
      }
    }

    .card {
      display: flex;
      flex-direction: column;
      gap: var(--freyja-space-3);

      p {
        margin: 0;
        color: var(--freyja-text-muted);
      }
    }

    .number {
      color: var(--freyja-gold);
      font-family: var(--freyja-font-serif);
      font-size: var(--freyja-text-size-xl);
    }
  `,
})
export class Problems {
  protected readonly content = PROBLEMS;
}
