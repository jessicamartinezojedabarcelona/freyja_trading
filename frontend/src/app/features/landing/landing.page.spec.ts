import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';

import { FAQ, HERO } from './landing.content';
import { LandingPage } from './landing.page';

const squash = (element: Element | null | undefined) =>
  (element?.textContent ?? '').replace(/\s+/g, ' ').trim();

describe('LandingPage', () => {
  let fixture: ComponentFixture<LandingPage>;
  let root: HTMLElement;
  let httpMock: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideRouter([]), provideHttpClient(), provideHttpClientTesting()],
    });
    httpMock = TestBed.inject(HttpTestingController);
    fixture = TestBed.createComponent(LandingPage);
    fixture.detectChanges();
    root = fixture.nativeElement as HTMLElement;
  });

  afterEach(() => {
    httpMock.verify(); // a public page asks the server for nothing
  });

  const link = (label: string): HTMLAnchorElement =>
    [...root.querySelectorAll<HTMLAnchorElement>('a')].find((a) => squash(a) === label)!;

  describe('structure', () => {
    it('leads with one h1 that states the promise, then a heading per section', () => {
      const h1 = root.querySelectorAll('h1');
      expect(h1).toHaveLength(1);
      expect(squash(h1[0])).toBe(HERO.title);
      expect(root.querySelectorAll('h2')).toHaveLength(7); // one per section after the hero
    });

    it('contains the sections in reading order', () => {
      const order = [
        'app-site-header',
        'app-hero',
        'app-trust-strip',
        'app-problems',
        'app-benefits',
        'app-how-it-works',
        'app-use-cases',
        'app-principles',
        'app-faq',
        'app-final-cta',
        'app-site-footer',
      ];
      const found = [...root.querySelectorAll(order.join(','))].map((e) => e.tagName.toLowerCase());
      expect(found).toEqual(order);
    });

    it('starts with a skip link that lands on the main content', () => {
      const first = root.querySelector('a');
      expect(first?.classList.contains('skip-link')).toBe(true);
      expect(first?.getAttribute('href')).toBe('#contenido');
      expect(root.querySelector('main#contenido')).not.toBeNull();
    });

    it('gives every section its accessible name', () => {
      for (const section of root.querySelectorAll('section[aria-labelledby]')) {
        const id = section.getAttribute('aria-labelledby')!;
        expect(root.querySelector(`#${id}`), id).not.toBeNull();
      }
    });
  });

  describe('calls to action', () => {
    it('the main action creates an account, and the second one explains how it works', () => {
      const primary = root.querySelector<HTMLAnchorElement>('.hero .btn--primary')!;
      expect(squash(primary)).toBe('Crear cuenta');
      expect(primary.getAttribute('href')).toBe('/register');
      const secondary = link('Ver cómo funciona');
      expect(secondary.getAttribute('href')).toBe('#como-funciona');
      expect(root.querySelector('#como-funciona')).not.toBeNull();
    });

    it('"Entrar" leaves the decision to the session guard by pointing at the application', () => {
      expect(link('Entrar').getAttribute('href')).toBe('/dashboard');
    });

    it('closes with a strong action and a way in for people who already have an account', () => {
      const panel = root.querySelector('app-final-cta')!;
      expect(squash(panel.querySelector('.btn--primary'))).toBe('Crear cuenta');
      expect(panel.querySelector('.btn--primary')?.getAttribute('href')).toBe('/register');
      expect(panel.querySelector('a[href="/login"]')?.textContent).toContain('Ya tengo cuenta');
    });

    it('offers exactly one primary action per block, never two competing ones', () => {
      for (const block of root.querySelectorAll('app-site-header, app-hero, app-final-cta')) {
        expect(block.querySelectorAll('.btn--primary').length).toBe(1);
      }
    });

    it('links each navigation entry to a section that exists', () => {
      const anchors = [...root.querySelectorAll<HTMLAnchorElement>('app-site-header .links a')].map(
        (a) => a.getAttribute('href'),
      );
      expect(anchors).toEqual(['#como-funciona', '#datos-y-calidad', '#preguntas']);
      for (const href of anchors) {
        expect(root.querySelector(href!), href!).not.toBeNull();
      }
    });
  });

  describe('honesty', () => {
    it('labels the hero picture as an illustration, not as market data', () => {
      const figure = root.querySelector('app-hero-preview figure')!;
      expect(squash(figure.querySelector('figcaption'))).toBe(
        'Ilustración del explorador de mercado. No muestra datos reales.',
      );
      expect(squash(figure.querySelector('.window'))).toContain('Ilustración');
      // A screen reader gets the caption, not a meaningless shape of candles.
      expect(figure.querySelector('.window')?.getAttribute('aria-hidden')).toBe('true');
    });

    it('tells apart what exists from what is coming', () => {
      const text = squash(root);
      expect(text).toContain('Disponible');
      expect(text).toContain('Próximamente');
      const soon = [...root.querySelectorAll('app-availability-tag .chip')].filter((chip) =>
        squash(chip).includes('Próximamente'),
      );
      expect(soon.length).toBeGreaterThanOrEqual(4);
    });

    it('shows a risk notice in the footer', () => {
      const risk = root.querySelector('footer [role="note"]')!;
      expect(squash(risk)).toContain('Aviso de riesgo');
      expect(squash(risk)).toContain('riesgo de pérdida');
      expect(squash(risk)).toContain('no es asesoramiento financiero');
    });

    it('has no testimonials', () => {
      expect(squash(root).toLowerCase()).not.toContain('testimonio');
      expect(squash(root.querySelector('app-principles'))).toContain('Lo que Freyja no hará nunca');
    });

    it('states facts, not profit figures', () => {
      const strip = squash(root.querySelector('app-trust-strip'));
      expect(strip).toContain('pares cripto disponibles hoy');
      expect(strip).not.toMatch(/%\s*(anual|mensual|de retorno)|rentab/i);
    });
  });

  describe('FAQ', () => {
    it('shows every question collapsed, and opens with the keyboard-friendly native control', () => {
      const items = [...root.querySelectorAll<HTMLDetailsElement>('app-faq details')];
      expect(items).toHaveLength(FAQ.items.length);
      expect(items.every((item) => !item.open)).toBe(true);

      items[0].open = true;
      expect(items[0].open).toBe(true);
      expect(squash(items[0].querySelector('summary'))).toBe(FAQ.items[0].question);
      expect(squash(items[0])).toContain(FAQ.items[0].answer);
    });
  });
});
