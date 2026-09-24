import { Component } from '@angular/core';
import { RouterLink } from '@angular/router';

import { Brand } from '../../shared/brand/brand';
import { NAV_LINKS } from './landing.content';

/** Sticky header of the public pages. "Entrar" goes to the application: the
 * session guard sends people without a session to the login screen. */
@Component({
  selector: 'app-site-header',
  imports: [RouterLink, Brand],
  template: `
    <header class="header">
      <div class="container bar">
        <a routerLink="/" class="brand-link" aria-label="Freyja: inicio">
          <app-brand />
        </a>

        <nav class="links" aria-label="Secciones de la página">
          @for (link of links; track link.href) {
            <a [href]="link.href">{{ link.label }}</a>
          }
        </nav>

        <div class="actions">
          <a class="btn btn--ghost btn--sm" routerLink="/dashboard">Entrar</a>
          <a class="btn btn--primary btn--sm" routerLink="/register">Crear cuenta</a>
        </div>
      </div>
    </header>
  `,
  styles: `
    .header {
      position: sticky;
      top: 0;
      z-index: 20;
      background: color-mix(in srgb, var(--freyja-bg) 82%, transparent);
      backdrop-filter: blur(10px);
      border-bottom: 1px solid var(--freyja-border-subtle);
    }

    .bar {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: var(--freyja-space-4);
      height: var(--freyja-header-height);
    }

    .brand-link {
      color: inherit;
      text-decoration: none;
    }

    .links {
      display: none;
      gap: var(--freyja-space-6);

      a {
        color: var(--freyja-text-muted);
        font-size: var(--freyja-text-size-sm);
        text-decoration: none;
        transition: color var(--freyja-motion-fast);

        &:hover {
          color: var(--freyja-text-cream);
        }
      }

      @media (min-width: 48rem) {
        display: flex;
      }
    }

    .actions {
      display: flex;
      gap: var(--freyja-space-2);

      .btn {
        white-space: nowrap;
      }
    }
  `,
})
export class SiteHeader {
  protected readonly links = NAV_LINKS;
}
