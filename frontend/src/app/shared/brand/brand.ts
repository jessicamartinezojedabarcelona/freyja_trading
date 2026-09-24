import { Component, input } from '@angular/core';

import { RuneMark } from '../rune-mark/rune-mark';

/** Freyja's mark and wordmark, for headers and footers. `size` scales both. */
@Component({
  selector: 'app-brand',
  imports: [RuneMark],
  template: `
    <span class="brand" [class.brand--lg]="size() === 'lg'">
      <span class="emblem" aria-hidden="true">
        <svg viewBox="0 0 100 100" class="ring" xmlns="http://www.w3.org/2000/svg">
          <circle cx="50" cy="50" r="46" />
        </svg>
        <app-rune-mark class="rune" aria-hidden="true" />
      </span>
      <span class="wordmark">Freyja</span>
    </span>
  `,
  styles: `
    :host {
      display: inline-block;
    }

    .brand {
      --emblem: 2rem;
      display: inline-flex;
      align-items: center;
      gap: var(--freyja-space-3);
      color: var(--freyja-text-cream);
    }

    .brand--lg {
      --emblem: 3rem;
    }

    .emblem {
      position: relative;
      width: var(--emblem);
      height: var(--emblem);
      flex: none;
      filter: drop-shadow(0 0 0.4rem rgba(201, 162, 74, 0.4));
    }

    .ring {
      display: block;
      width: 100%;
      height: 100%;

      circle {
        fill: var(--freyja-bg);
        stroke: var(--freyja-border-strong);
        stroke-width: 3;
      }
    }

    .rune {
      position: absolute;
      top: 50%;
      left: 50%;
      width: 58%;
      color: var(--freyja-gold-bright);
      transform: translate(-50%, -50%);
    }

    .wordmark {
      font-family: var(--freyja-font-serif);
      font-size: calc(var(--emblem) * 0.62);
      font-weight: 600;
      letter-spacing: 0.3em;
      text-transform: uppercase;
    }
  `,
})
export class Brand {
  readonly size = input<'md' | 'lg'>('md');
}
