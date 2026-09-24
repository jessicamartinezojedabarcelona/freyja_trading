import { Component } from '@angular/core';

import { FACTS } from './landing.content';

/** A band of facts about the product today. They are not performance numbers:
 * see FACTS in landing.content.ts. */
@Component({
  selector: 'app-trust-strip',
  template: `
    <section class="strip" aria-label="Freyja hoy, en cifras">
      <dl class="container facts">
        @for (fact of facts; track fact.label) {
          <div class="fact">
            <dt class="label">{{ fact.label }}</dt>
            <dd class="value">{{ fact.value }}</dd>
          </div>
        }
      </dl>
    </section>
  `,
  styles: `
    .strip {
      background: color-mix(in srgb, var(--freyja-card-bg) 60%, transparent);
      border-block: 1px solid var(--freyja-border-subtle);
    }

    .facts {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: var(--freyja-space-6) var(--freyja-space-5);
      margin-block: 0;
      padding-block: var(--freyja-space-7);

      @media (min-width: 48rem) {
        grid-template-columns: repeat(4, minmax(0, 1fr));
      }
    }

    .fact {
      display: flex;
      flex-direction: column-reverse; /* value first for the eye, label first for a screen reader */
      gap: var(--freyja-space-1);
    }

    .value {
      margin: 0;
      color: var(--freyja-gold-bright);
      font-family: var(--freyja-font-serif);
      font-size: clamp(2rem, 4vw, 2.75rem);
      line-height: 1;
    }

    .label {
      color: var(--freyja-text-muted);
      font-size: var(--freyja-text-size-sm);
    }
  `,
})
export class TrustStrip {
  protected readonly facts = FACTS;
}
