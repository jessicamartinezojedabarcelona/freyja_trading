import { Component } from '@angular/core';

import { FAQ } from './landing.content';

/** Questions and answers with native <details>: keyboard and screen-reader
 * friendly without any script. */
@Component({
  selector: 'app-faq',
  template: `
    <section class="section" [id]="content.id" aria-labelledby="faq-title">
      <div class="container narrow">
        <header class="section__header">
          <p class="eyebrow">{{ content.eyebrow }}</p>
          <h2 id="faq-title" class="heading-section">{{ content.title }}</h2>
        </header>

        <div class="list">
          @for (item of content.items; track item.question) {
            <details class="item">
              <summary>
                <span>{{ item.question }}</span>
                <span class="plus" aria-hidden="true"></span>
              </summary>
              <p>{{ item.answer }}</p>
            </details>
          }
        </div>
      </div>
    </section>
  `,
  styles: `
    .narrow {
      max-width: 52rem;
    }

    .list {
      border-top: 1px solid var(--freyja-border-subtle);
    }

    .item {
      border-bottom: 1px solid var(--freyja-border-subtle);
    }

    summary {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: var(--freyja-space-4);
      padding-block: var(--freyja-space-5);
      font-family: var(--freyja-font-serif);
      font-size: var(--freyja-text-size-lg);
      cursor: pointer;
      list-style: none;
      transition: color var(--freyja-motion-fast);

      &::-webkit-details-marker {
        display: none;
      }

      &:hover {
        color: var(--freyja-gold-bright);
      }
    }

    /* A plus that turns into a minus when open. */
    .plus {
      position: relative;
      flex: none;
      width: 1rem;
      height: 1rem;

      &::before,
      &::after {
        position: absolute;
        top: 50%;
        left: 0;
        width: 100%;
        height: 2px;
        content: '';
        background: var(--freyja-gold);
        transition: transform var(--freyja-motion-base);
      }

      &::after {
        transform: rotate(90deg);
      }
    }

    details[open] .plus::after {
      transform: rotate(0);
    }

    p {
      max-width: 42rem;
      margin: 0;
      padding-bottom: var(--freyja-space-5);
      color: var(--freyja-text-muted);
    }
  `,
})
export class Faq {
  protected readonly content = FAQ;
}
