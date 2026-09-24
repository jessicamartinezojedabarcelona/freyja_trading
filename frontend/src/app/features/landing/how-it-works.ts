import { Component } from '@angular/core';

import { AvailabilityTag } from './availability-tag';
import { HOW_IT_WORKS } from './landing.content';

@Component({
  selector: 'app-how-it-works',
  imports: [AvailabilityTag],
  template: `
    <section class="section" [id]="content.id" aria-labelledby="how-title">
      <div class="container">
        <header class="section__header">
          <p class="eyebrow">{{ content.eyebrow }}</p>
          <h2 id="how-title" class="heading-section">{{ content.title }}</h2>
        </header>

        <ol class="steps">
          @for (step of content.steps; track step.title; let index = $index) {
            <li class="step">
              <span class="badge" aria-hidden="true">{{ index + 1 }}</span>
              <div class="body">
                <app-availability-tag [value]="step.availability" />
                <h3 class="heading-card">{{ step.title }}</h3>
                <p>{{ step.text }}</p>
              </div>
            </li>
          }
        </ol>
      </div>
    </section>
  `,
  styles: `
    .steps {
      display: grid;
      gap: var(--freyja-space-6);
      margin: 0;
      padding: 0;
      list-style: none;

      @media (min-width: 56rem) {
        grid-template-columns: repeat(3, minmax(0, 1fr));
        gap: var(--freyja-space-5);
      }
    }

    .step {
      display: flex;
      gap: var(--freyja-space-4);
      padding: var(--freyja-space-5);
      background: var(--freyja-card-bg);
      border: 1px solid var(--freyja-border-subtle);
      border-radius: var(--freyja-radius-md);

      @media (min-width: 56rem) {
        flex-direction: column;
      }
    }

    .badge {
      display: grid;
      flex: none;
      width: 2.75rem;
      height: 2.75rem;
      place-items: center;
      color: var(--freyja-gold-bright);
      font-family: var(--freyja-font-serif);
      font-size: var(--freyja-text-size-lg);
      border: 1px solid var(--freyja-border-strong);
      border-radius: var(--freyja-radius-full);
    }

    .body {
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
export class HowItWorks {
  protected readonly content = HOW_IT_WORKS;
}
