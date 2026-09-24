import { Component } from '@angular/core';
import { RouterLink } from '@angular/router';

import { Brand } from '../../shared/brand/brand';
import { FOOTER } from './landing.content';

@Component({
  selector: 'app-site-footer',
  imports: [RouterLink, Brand],
  template: `
    <footer class="footer">
      <div class="container">
        <div class="top">
          <div class="about">
            <app-brand />
            <p>{{ content.tagline }}</p>
          </div>
          <nav class="links" aria-label="Enlaces del pie">
            <a routerLink="/login">Iniciar sesión</a>
            <a routerLink="/register">Crear cuenta</a>
          </nav>
        </div>

        <p class="risk" role="note"><strong>Aviso de riesgo.</strong> {{ content.risk }}</p>
        <p class="legal">© {{ year }} Freyja</p>
      </div>
    </footer>
  `,
  styles: `
    .footer {
      padding-block: var(--freyja-space-8) var(--freyja-space-6);
      border-top: 1px solid var(--freyja-border-subtle);
    }

    .top {
      display: flex;
      flex-wrap: wrap;
      align-items: flex-start;
      justify-content: space-between;
      gap: var(--freyja-space-6);
    }

    .about p {
      margin: var(--freyja-space-3) 0 0;
      color: var(--freyja-text-muted);
      font-size: var(--freyja-text-size-sm);
    }

    .links {
      display: flex;
      gap: var(--freyja-space-5);
      font-size: var(--freyja-text-size-sm);

      a {
        color: var(--freyja-text-muted);
        text-decoration: none;

        &:hover {
          color: var(--freyja-text-cream);
        }
      }
    }

    .risk {
      max-width: 52rem;
      margin: var(--freyja-space-7) 0 0;
      padding: var(--freyja-space-4);
      color: var(--freyja-text-muted);
      font-size: var(--freyja-text-size-sm);
      border: 1px solid var(--freyja-border-subtle);
      border-radius: var(--freyja-radius-md);

      strong {
        color: var(--freyja-text-cream);
      }
    }

    .legal {
      margin: var(--freyja-space-5) 0 0;
      color: var(--freyja-text-disabled);
      font-size: var(--freyja-text-size-xs);
    }
  `,
})
export class SiteFooter {
  protected readonly content = FOOTER;
  protected readonly year = new Date().getFullYear();
}
