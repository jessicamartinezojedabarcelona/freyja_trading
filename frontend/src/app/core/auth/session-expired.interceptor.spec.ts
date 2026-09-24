import { HttpClient, provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { Router } from '@angular/router';

import { API_BASE_URL } from '../config/api.config';
import { AuthService } from './auth.service';
import { sessionExpiredInterceptor } from './session-expired.interceptor';

const UNAUTHORIZED = { status: 401, statusText: 'Unauthorized' };

describe('sessionExpiredInterceptor', () => {
  let http: HttpClient;
  let httpMock: HttpTestingController;
  let auth: AuthService;
  let navigate: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    navigate = vi.fn().mockResolvedValue(true);
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(withInterceptors([sessionExpiredInterceptor])),
        provideHttpClientTesting(),
        { provide: Router, useValue: { navigate } },
      ],
    });
    http = TestBed.inject(HttpClient);
    httpMock = TestBed.inject(HttpTestingController);
    auth = TestBed.inject(AuthService);
  });

  afterEach(() => {
    httpMock.verify();
  });

  function signIn(): void {
    auth.login('owner@example.test', 'correct-horse-battery-staple').subscribe();
    httpMock
      .expectOne(`${API_BASE_URL}/auth/login`)
      .flush({ id: 'user-id', identifier: 'owner@example.test' });
  }

  it('sends the user to /login with the expired notice when a data call comes back 401', () => {
    signIn();
    let failed: number | undefined;
    http
      .get(`${API_BASE_URL}/market-data/candles`)
      .subscribe({ error: (e: { status: number }) => (failed = e.status) });

    httpMock.expectOne(`${API_BASE_URL}/market-data/candles`).flush({}, UNAUTHORIZED);

    expect(navigate).toHaveBeenCalledExactlyOnceWith(['/login'], {
      queryParams: { expired: '1' },
    });
    expect(auth.currentUser()).toBeNull(); // the stale user is not kept around
    expect(failed).toBe(401); // the caller still sees the error
  });

  it('does not claim the session expired when there never was one', () => {
    http.get(`${API_BASE_URL}/catalog/instruments`).subscribe({ error: () => undefined });

    httpMock.expectOne(`${API_BASE_URL}/catalog/instruments`).flush({}, UNAUTHORIZED);

    expect(navigate).toHaveBeenCalledExactlyOnceWith(['/login'], { queryParams: {} });
  });

  it('leaves a failed login alone: wrong credentials are not an expired session', () => {
    http.post(`${API_BASE_URL}/auth/login`, {}).subscribe({ error: () => undefined });

    httpMock.expectOne(`${API_BASE_URL}/auth/login`).flush({}, UNAUTHORIZED);

    expect(navigate).not.toHaveBeenCalled();
  });

  it.each([403, 404, 500, 0])('ignores a %s response', (status) => {
    signIn();
    http.get(`${API_BASE_URL}/market-data/candles`).subscribe({ error: () => undefined });

    httpMock
      .expectOne(`${API_BASE_URL}/market-data/candles`)
      .flush({}, { status, statusText: 'x' });

    expect(navigate).not.toHaveBeenCalled();
    expect(auth.currentUser()).not.toBeNull();
  });

  it('ignores a 401 from somewhere that is not the Freyja API', () => {
    signIn();
    http.get('https://unrelated.example.test/data').subscribe({ error: () => undefined });

    httpMock.expectOne('https://unrelated.example.test/data').flush({}, UNAUTHORIZED);

    expect(navigate).not.toHaveBeenCalled();
    expect(auth.currentUser()).not.toBeNull();
  });

  it('passes successful responses through untouched', () => {
    let body: unknown;
    http.get(`${API_BASE_URL}/market-data/candles`).subscribe((b) => (body = b));

    httpMock.expectOne(`${API_BASE_URL}/market-data/candles`).flush({ ok: true });

    expect(body).toEqual({ ok: true });
    expect(navigate).not.toHaveBeenCalled();
  });
});
