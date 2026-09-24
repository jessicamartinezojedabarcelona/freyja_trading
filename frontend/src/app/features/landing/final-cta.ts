import { Component } from '@angular/core';
import { RouterLink } from '@angular/router';

import { FINAL_CTA } from './landing.content';

@Component({
  selector: 'app-final-cta',
  imports: [RouterLink],
  template: `
    <section class="section" aria-labelledby="final-title">
      <div class="container">
        <div class="panel">
          <h2 id="final-title" class="heading-section">{{ content.title }}</h2>
          <p class="lead">{{ content.text }}</p>
          <div class="ctas">
            <a class="btn btn--primary btn--lg" routerLink="/register">{{ content.primaryCta }}</a>
            <a class="btn btn--lg" routerLink="/login">{{ content.secondaryCta }}</a>
          </div>
        </div>
      </div>
    </section>
  `,
  styles: `
    .panel {
      padding: clamp(2rem, 6vw, 4.5rem) var(--freyja-space-5);
      text-align: center;
      background:
        radial-gradient(
          ellipse at 50% 0%,
          color-mix(in srgb, var(--freyja-gold) 14%, transparent),
          transparent 65%
        ),
        var(--freyja-card-bg);
      border: 1px solid var(--freyja-border);
      border-radius: var(--freyja-radius-lg);
      box-shadow: var(--freyja-glow-brand);
    }

    .lead {
      max-width: 34rem;
      margin: var(--freyja-space-4) auto 0;
    }

    .ctas {
      display: flex;
      flex-wrap: wrap;
      gap: var(--freyja-space-3);
      justify-content: center;
      margin-top: var(--freyja-space-6);
    }
  `,
})
export class FinalCta {
  protected readonly content = FINAL_CTA;
}
