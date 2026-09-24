import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { Router, provideRouter } from '@angular/router';

import { routes } from './app.routes';
import { API_BASE_URL } from './core/config/api.config';

// Freyja lets anyone create their own account, so registration — like login
// and password recovery — is a public route, while the application itself
// stays behind the session guard.
describe('app routes — public registration', () => {
  const publicPaths = ['register', 'login', 'forgot-password', 'reset-password'];

  let httpMock: HttpTestingController;
  let router: Router;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideRouter(routes), provideHttpClient(), provideHttpClientTesting()],
    });
    httpMock = TestBed.inject(HttpTestingController);
    router = TestBed.inject(Router);
  });

  afterEach(() => {
    httpMock.verify();
  });

  it('declares the /register route', () => {
    expect(routes.map((route) => route.path)).toContain('register');
  });

  it('keeps registration, login and password recovery public (no session guard)', () => {
    for (const path of publicPaths) {
      const route = routes.find((candidate) => candidate.path === path);
      expect(route, path).toBeDefined();
      expect(route?.canActivate, path).toBeUndefined();
    }
  });

  it('keeps the application itself behind the session guard', () => {
    const root = routes.find((route) => route.path === '');
    expect(root?.canActivate?.length).toBeGreaterThan(0);
  });

  it('lets an anonymous visitor open /register without asking for a session', async () => {
    await router.navigateByUrl('/register');

    expect(router.url).toBe('/register');
    httpMock.expectNone(`${API_BASE_URL}/auth/me`);
  });
});
