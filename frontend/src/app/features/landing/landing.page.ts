import { Component } from '@angular/core';

import { Benefits } from './benefits';
import { Faq } from './faq';
import { FinalCta } from './final-cta';
import { Hero } from './hero';
import { HowItWorks } from './how-it-works';
import { Principles } from './principles';
import { Problems } from './problems';
import { SiteFooter } from './site-footer';
import { SiteHeader } from './site-header';
import { TrustStrip } from './trust-strip';
import { UseCases } from './use-cases';

/** Public landing page (`/`). Each block is its own component: reorder, remove or
 * restyle a section by editing this list or that section's file. The words live in
 * landing.content.ts; spacing and colours in src/styles/. */
@Component({
  selector: 'app-landing-page',
  imports: [
    SiteHeader,
    Hero,
    TrustStrip,
    Problems,
    Benefits,
    HowItWorks,
    UseCases,
    Principles,
    Faq,
    FinalCta,
    SiteFooter,
  ],
  template: `
    <a class="skip-link" href="#contenido">Saltar al contenido</a>
    <app-site-header />
    <main id="contenido" tabindex="-1">
      <app-hero />
      <app-trust-strip />
      <app-problems />
      <app-benefits />
      <app-how-it-works />
      <app-use-cases />
      <app-principles />
      <app-faq />
      <app-final-cta />
    </main>
    <app-site-footer />
  `,
  styles: `
    :host {
      display: block;
      min-height: 100vh;
      background:
        radial-gradient(ellipse at 50% -5%, var(--freyja-bg-glow) 0%, transparent 60%),
        var(--freyja-bg);
      color: var(--freyja-text-cream);
    }

    main:focus {
      outline: none;
    }
  `,
})
export class LandingPage {}
