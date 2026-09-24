import { Component } from '@angular/core';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { Router, provideRouter } from '@angular/router';
import { RouterTestingHarness } from '@angular/router/testing';

import { AuthService } from '../../core/auth/auth.service';
import { API_BASE_URL } from '../../core/config/api.config';
import { AppShell } from './app-shell';

@Component({ template: '<p class="page">Contenido de la página</p>' })
class DummyPage {}

const squash = (element: Element | null | undefined) =>
  (element?.textContent ?? '').replace(/\s+/g, ' ').trim();

describe('AppShell', () => {
  let httpMock: HttpTestingController;
  let harness: RouterTestingHarness;

  const root = () => harness.fixture.nativeElement as HTMLElement;
  const sidebar = () => root().querySelector<HTMLElement>('aside.sidebar')!;
  const menuButton = () => root().querySelector<HTMLButtonElement>('.menu-button')!;

  async function open(url = '/dashboard'): Promise<void> {
    TestBed.configureTestingModule({
      providers: [
        provideRouter([
          {
            path: '',
            component: AppShell,
            children: [
              { path: 'dashboard', component: DummyPage },
              { path: 'mercados', component: DummyPage },
              { path: 'mercados/:instrumentId', component: DummyPage },
            ],
          },
        ]),
        provideHttpClient(),
        provideHttpClientTesting(),
      ],
    });
    httpMock = TestBed.inject(HttpTestingController);
    harness = await RouterTestingHarness.create();
    await harness.navigateByUrl(url);
    harness.detectChanges();
  }

  afterEach(() => {
    httpMock.verify();
  });

  it('shows the page inside the shell', async () => {
    await open();
    expect(root().querySelector('main#contenido .page')?.textContent).toContain(
      'Contenido de la página',
    );
  });

  it('starts with a skip link to the content', async () => {
    await open();
    const first = root().querySelector('a');
    expect(first?.classList.contains('skip-link')).toBe(true);
    expect(first?.getAttribute('href')).toBe('#contenido');
    expect(root().querySelector('main')?.id).toBe('contenido');
  });

  describe('navigation', () => {
    it('links the screens that exist, in a labelled navigation', async () => {
      await open();
      const nav = root().querySelector('nav[aria-label="Principal"]')!;
      const links = [...nav.querySelectorAll('a')].map((a) => [squash(a), a.getAttribute('href')]);

      expect(links).toEqual([
        ['Dashboard', '/dashboard'],
        ['Mercados', '/mercados'],
      ]);
    });

    it('marks the current screen for assistive technology and with the gold indicator', async () => {
      await open('/dashboard');
      const current = root().querySelectorAll('nav a[aria-current="page"]');

      expect(current).toHaveLength(1);
      expect(squash(current[0])).toBe('Dashboard');
      expect(current[0].classList.contains('nav-item--active')).toBe(true);
    });

    it('keeps Mercados active on an instrument page', async () => {
      await open('/mercados/abc');
      const current = root().querySelector('nav a[aria-current="page"]');
      expect(squash(current)).toBe('Mercados');
    });

    it('lists what is still to come as locked entries, not as links', async () => {
      await open();
      const upcoming = root().querySelector('section.upcoming')!;
      const items = [...upcoming.querySelectorAll('.nav-item--locked')].map((item) => squash(item));

      expect(items).toHaveLength(6);
      expect(items.every((text) => text.includes('(aún no disponible)'))).toBe(true);
      expect(items.join(' ')).toContain('Backtesting');
      expect(upcoming.querySelectorAll('a')).toHaveLength(0);
      expect(squash(upcoming.querySelector('h2'))).toBe('Próximamente');
    });
  });

  describe('account', () => {
    it('shows who is signed in once known', async () => {
      await open();
      TestBed.inject(AuthService).me().subscribe();
      httpMock
        .expectOne(`${API_BASE_URL}/auth/me`)
        .flush({ id: 'user-id', identifier: 'owner@example.test' });
      harness.detectChanges();

      expect(squash(root().querySelector('.who'))).toContain('owner@example.test');
    });

    it('shows nothing about the account until the session is known', async () => {
      await open();
      expect(root().querySelector('.who')).toBeNull();
    });

    it('signs out and goes to the login screen', async () => {
      await open();
      const router = TestBed.inject(Router);
      const navigate = vi.spyOn(router, 'navigateByUrl').mockResolvedValue(true);

      [...root().querySelectorAll<HTMLButtonElement>('.account button')]
        .find((b) => squash(b) === 'Cerrar sesión')!
        .click();
      httpMock.expectOne(`${API_BASE_URL}/auth/logout`).flush(null);

      expect(navigate).toHaveBeenCalledWith('/login');
    });
  });

  describe('menu on a phone', () => {
    it('is closed at first and says so', async () => {
      await open();
      expect(menuButton().getAttribute('aria-expanded')).toBe('false');
      expect(menuButton().getAttribute('aria-controls')).toBe('menu-principal');
      expect(sidebar().id).toBe('menu-principal');
      expect(sidebar().classList.contains('sidebar--open')).toBe(false);
      expect(root().querySelector('.backdrop')).toBeNull();
    });

    it('opens and closes with its button', async () => {
      await open();

      menuButton().click();
      harness.detectChanges();
      expect(menuButton().getAttribute('aria-expanded')).toBe('true');
      expect(sidebar().classList.contains('sidebar--open')).toBe(true);
      expect(root().querySelector('.backdrop')).not.toBeNull();

      menuButton().click();
      harness.detectChanges();
      expect(sidebar().classList.contains('sidebar--open')).toBe(false);
    });

    it('closes with Escape', async () => {
      await open();
      menuButton().click();
      harness.detectChanges();

      document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }));
      harness.detectChanges();

      expect(sidebar().classList.contains('sidebar--open')).toBe(false);
    });

    it('closes when the dimmed background is pressed', async () => {
      await open();
      menuButton().click();
      harness.detectChanges();

      root().querySelector<HTMLButtonElement>('.backdrop')!.click();
      harness.detectChanges();

      expect(sidebar().classList.contains('sidebar--open')).toBe(false);
      expect(root().querySelector('.backdrop')).toBeNull();
    });

    it('closes after choosing a screen', async () => {
      await open();
      menuButton().click();
      harness.detectChanges();

      root().querySelector<HTMLAnchorElement>('nav a[href="/mercados"]')!.click();
      await harness.fixture.whenStable();
      harness.detectChanges();

      expect(sidebar().classList.contains('sidebar--open')).toBe(false);
    });
  });
});
