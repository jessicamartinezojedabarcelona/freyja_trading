import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { Router, UrlTree, provideRouter } from '@angular/router';
import { Observable, firstValueFrom } from 'rxjs';

import { API_BASE_URL } from '../config/api.config';
import { authGuard } from './auth.guard';
import { AuthService } from './auth.service';

describe('authGuard', () => {
  let httpMock: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideRouter([]), provideHttpClient(), provideHttpClientTesting()],
    });
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    httpMock.verify();
  });

  function runGuard(): Observable<boolean | UrlTree> {
    return TestBed.runInInjectionContext(() => authGuard({} as never, {} as never)) as Observable<
      boolean | UrlTree
    >;
  }

  it('allows activation when the session is valid', async () => {
    const resultPromise = firstValueFrom(runGuard());

    httpMock
      .expectOne(`${API_BASE_URL}/auth/me`)
      .flush({ id: 'user-id', identifier: 'owner@example.test' });

    expect(await resultPromise).toBe(true);
  });

  it('redirects to /login when there is no valid session', async () => {
    const resultPromise = firstValueFrom(runGuard());

    httpMock
      .expectOne(`${API_BASE_URL}/auth/me`)
      .flush({ detail: 'No autenticado.' }, { status: 401, statusText: 'Unauthorized' });

    const result = await resultPromise;
    expect(result).toBeInstanceOf(UrlTree);
    const router = TestBed.inject(Router);
    expect(router.serializeUrl(result as UrlTree)).toBe('/login');
  });

  it('redirects to /login?expired=1 when a previously known session becomes invalid', async () => {
    const authService = TestBed.inject(AuthService);
    authService.me().subscribe();
    httpMock
      .expectOne(`${API_BASE_URL}/auth/me`)
      .flush({ id: 'user-id', identifier: 'owner@example.test' });

    const resultPromise = firstValueFrom(runGuard());
    httpMock
      .expectOne(`${API_BASE_URL}/auth/me`)
      .flush({ detail: 'No autenticado.' }, { status: 401, statusText: 'Unauthorized' });

    const result = await resultPromise;
    const router = TestBed.inject(Router);
    expect(router.serializeUrl(result as UrlTree)).toBe('/login?expired=1');
  });
});
