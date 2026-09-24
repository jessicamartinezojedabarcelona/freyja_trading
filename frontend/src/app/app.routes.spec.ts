import { provideHttpClient } from '@angular/common/http';
import {
  HttpTestingController,
  TestRequest,
  provideHttpClientTesting,
} from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { Router, provideRouter } from '@angular/router';

import { routes } from './app.routes';
import { API_BASE_URL } from './core/config/api.config';

// AUTH-PRIVATE-ACCESS-001: Freyja 2.0 is private — accounts are provisioned
// by Jessica, never self-registered. Hiding the link is not enough: there
// must be no registration route at all.
describe('app routes — private access', () => {
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

  // The wildcard redirect sends the navigation to the protected root, whose
  // authGuard then asks the backend for the session — asynchronously.
  async function nextSessionRequest(): Promise<TestRequest> {
    for (let attempt = 0; attempt < 100; attempt++) {
      const [request] = httpMock.match(`${API_BASE_URL}/auth/me`);
      if (request) {
        return request;
      }
      await new Promise((resolve) => setTimeout(resolve, 0));
    }
    throw new Error('authGuard never asked the backend for the session');
  }

  it('declares no registration route', () => {
    const paths = routes.map((route) => route.path);
    expect(paths.some((path) => /regist|sign-?up/i.test(path ?? ''))).toBe(false);
  });

  it('keeps login and password recovery reachable', () => {
    const paths = routes.map((route) => route.path);
    expect(paths).toEqual(expect.arrayContaining(['login', 'forgot-password', 'reset-password']));
  });

  it('sends an anonymous visitor who opens /register to /login', async () => {
    const navigation = router.navigateByUrl('/register');

    (await nextSessionRequest()).flush(
      { detail: 'No autenticado.' },
      { status: 401, statusText: 'Unauthorized' },
    );

    await navigation;
    expect(router.url).toBe('/login');
  });

  it('never shows a registration screen to a signed-in account either', async () => {
    const navigation = router.navigateByUrl('/register');

    (await nextSessionRequest()).flush({ id: 'user-id', identifier: 'account@example.test' });

    await navigation;
    expect(router.url).toBe('/');
  });
});
