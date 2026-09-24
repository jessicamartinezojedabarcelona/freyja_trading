import { Component } from '@angular/core';
import { RouterLink } from '@angular/router';

interface UpcomingArea {
  title: string;
  description: string;
}

/** First screen after signing in. It shows only what exists today: a way into the
 * market explorer and an honest note on execution. No figure appears here until
 * it has a defined source and timestamp (UX-DASHBOARD rule), so the areas still
 * to come are described, not simulated. */
@Component({
  selector: 'app-dashboard-page',
  imports: [RouterLink],
  template: `
    <header class="page-header">
      <p class="eyebrow">Tu panel</p>
      <h1 class="heading-section">Dashboard</h1>
      <p class="lead">
        Aquí verás el estado de tu actividad en Freyja. Hoy puedes explorar el mercado; el resto de
        áreas se irán habilitando y aparecerán aquí.
      </p>
    </header>

    <div class="grid">
      <article class="card card--interactive featured">
        <div class="card-top">
          <h2 class="heading-card">Explorar el mercado</h2>
          <span class="chip chip--success"><span aria-hidden="true">✓</span> Disponible</span>
        </div>
        <p>
          Velas cerradas de los pares cripto disponibles, con su fuente, su frescura y su calidad
          siempre a la vista.
        </p>
        <a class="btn btn--primary" routerLink="/mercados">Abrir Mercados</a>
      </article>

      <article class="card status">
        <div class="card-top">
          <h2 class="heading-card">Operativa</h2>
          <span class="chip chip--blocked"
            ><span aria-hidden="true">🔒</span> REAL · Bloqueada</span
          >
        </div>
        <p>
          Freyja no ejecuta operaciones reales. Solo se habilitará cuando supere los requisitos
          técnicos, de seguridad y de validación. El modo DEMO llegará antes.
        </p>
      </article>

      @for (area of upcoming; track area.title) {
        <article class="card soon">
          <div class="card-top">
            <h2 class="heading-card">{{ area.title }}</h2>
            <span class="chip"><span aria-hidden="true">🔒</span> Próximamente</span>
          </div>
          <p>{{ area.description }}</p>
        </article>
      }
    </div>
  `,
  styles: `
    :host {
      display: block;
      max-width: 72rem;
    }

    .page-header {
      max-width: 44rem;
      margin-bottom: var(--freyja-space-7);
    }

    .page-header .lead {
      margin: var(--freyja-space-3) 0 0;
    }

    .grid {
      display: grid;
      gap: var(--freyja-space-4);
      grid-template-columns: repeat(auto-fill, minmax(min(100%, 19rem), 1fr));
    }

    .card {
      display: flex;
      flex-direction: column;
      gap: var(--freyja-space-4);

      p {
        margin: 0;
        color: var(--freyja-text-muted);
      }
    }

    .card-top {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      justify-content: space-between;
      gap: var(--freyja-space-2);
    }

    .featured {
      border-color: var(--freyja-border);
      background:
        linear-gradient(
          160deg,
          color-mix(in srgb, var(--freyja-gold) 8%, transparent),
          transparent 60%
        ),
        var(--freyja-card-bg);

      .btn {
        align-self: flex-start;
        margin-top: auto;
      }
    }

    .soon {
      opacity: 0.8;
    }
  `,
})
export class DashboardPage {
  protected readonly upcoming: readonly UpcomingArea[] = [
    {
      title: 'Oportunidades',
      description: 'Señales explicadas, con la evidencia que las produjo y su vigencia.',
    },
    {
      title: 'Estrategias',
      description: 'Reglas definidas y versionadas, para que un resultado se pueda reproducir.',
    },
    {
      title: 'Backtesting',
      description: 'Pruebas históricas con comisiones, spread y calidad de datos, sin promesas.',
    },
    {
      title: 'Riesgo y cartera',
      description: 'Límites de riesgo que no se pueden ampliar y seguimiento de posiciones.',
    },
  ];
}
