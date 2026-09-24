import { Component } from '@angular/core';
import { RouterLink } from '@angular/router';

import { HeroPreview } from './hero-preview';
import { HERO } from './landing.content';

/** The first thing a visitor sees: the promise, one clear action, and a picture
 * of the product. Spacing and columns are set with the variables at the top of
 * the styles so they are quick to retouch. */
@Component({
  selector: 'app-hero',
  imports: [RouterLink, HeroPreview],
  template: `
    <section class="hero" aria-labelledby="hero-title">
      <div class="container grid">
        <div class="copy">
          <p class="eyebrow">{{ hero.eyebrow }}</p>
          <h1 id="hero-title" class="heading-display">{{ hero.title }}</h1>
          <p class="lead">{{ hero.lead }}</p>

          <div class="ctas">
            <a class="btn btn--primary btn--lg" routerLink="/register">{{ hero.primaryCta }}</a>
            <a class="btn btn--lg" href="#como-funciona">{{ hero.secondaryCta }}</a>
          </div>
          <p class="note">{{ hero.note }}</p>

          <ul class="assurances" aria-label="Garantías de los datos">
            @for (item of hero.assurances; track item) {
              <li><span aria-hidden="true">✓</span> {{ item }}</li>
            }
          </ul>
        </div>

        <app-hero-preview class="visual" />
      </div>
    </section>
  `,
  styles: `
    :host {
      --hero-gap: var(--freyja-space-8);
      --hero-padding-top: clamp(2.5rem, 7vw, 5.5rem);
      --hero-padding-bottom: clamp(3rem, 8vw, 6rem);
      display: block;
    }

    .hero {
      padding-top: var(--hero-padding-top);
      padding-bottom: var(--hero-padding-bottom);
      background: radial-gradient(
        ellipse 60% 55% at 78% 30%,
        color-mix(in srgb, var(--freyja-gold) 13%, transparent),
        transparent 70%
      );
    }

    .grid {
      display: grid;
      gap: var(--hero-gap);
      align-items: center;

      @media (min-width: 60rem) {
        grid-template-columns: minmax(0, 1.05fr) minmax(0, 0.95fr);
      }
    }

    .lead {
      max-width: 34rem;
      margin: var(--freyja-space-5) 0 0;
    }

    .ctas {
      display: flex;
      flex-wrap: wrap;
      gap: var(--freyja-space-3);
      margin-top: var(--freyja-space-6);
    }

    .note {
      margin: var(--freyja-space-4) 0 0;
      color: var(--freyja-text-muted);
      font-size: var(--freyja-text-size-sm);
    }

    .assurances {
      display: flex;
      flex-wrap: wrap;
      gap: var(--freyja-space-2) var(--freyja-space-5);
      margin: var(--freyja-space-6) 0 0;
      padding: 0;
      color: var(--freyja-text-cream);
      font-size: var(--freyja-text-size-sm);
      list-style: none;

      span {
        color: var(--freyja-status-success);
      }
    }
  `,
})
export class Hero {
  protected readonly hero = HERO;
}
