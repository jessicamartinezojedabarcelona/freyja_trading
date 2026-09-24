import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';

import { DashboardPage } from './dashboard.page';

const squash = (element: Element | null | undefined) =>
  (element?.textContent ?? '').replace(/\s+/g, ' ').trim();

describe('DashboardPage', () => {
  function render(): HTMLElement {
    TestBed.configureTestingModule({ providers: [provideRouter([])] });
    const fixture = TestBed.createComponent(DashboardPage);
    fixture.detectChanges();
    return fixture.nativeElement as HTMLElement;
  }

  it('has one h1 and explains what the screen is for', () => {
    const root = render();
    expect(root.querySelectorAll('h1')).toHaveLength(1);
    expect(squash(root.querySelector('h1'))).toBe('Dashboard');
    expect(squash(root)).toContain('Hoy puedes explorar el mercado');
  });

  it('offers the one thing that exists today, with a single primary action', () => {
    const root = render();
    const featured = root.querySelector('.featured')!;

    expect(squash(featured)).toContain('Explorar el mercado');
    expect(squash(featured)).toContain('Disponible');
    const action = featured.querySelector<HTMLAnchorElement>('a.btn--primary')!;
    expect(squash(action)).toBe('Abrir Mercados');
    expect(action.getAttribute('href')).toBe('/mercados');
    expect(root.querySelectorAll('.btn--primary')).toHaveLength(1);
  });

  it('says plainly that real execution is blocked', () => {
    const status = render().querySelector('.status')!;
    expect(squash(status)).toContain('REAL · Bloqueada');
    expect(squash(status)).toContain('no ejecuta operaciones reales');
    expect(squash(status)).toContain('DEMO llegará antes');
  });

  it('describes the areas to come without linking or simulating them', () => {
    const root = render();
    const soon = [...root.querySelectorAll('.soon')];

    expect(soon.map((card) => squash(card.querySelector('h2')))).toEqual([
      'Oportunidades',
      'Estrategias',
      'Backtesting',
      'Riesgo y cartera',
    ]);
    for (const card of soon) {
      expect(squash(card)).toContain('Próximamente');
      expect(card.querySelectorAll('a, button')).toHaveLength(0);
    }
  });

  it('shows no figure at all: a number needs a source and a timestamp first', () => {
    expect(squash(render())).not.toMatch(/\d/);
  });
});
