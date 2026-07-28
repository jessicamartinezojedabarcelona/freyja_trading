import {
  HttpClient,
  HttpErrorResponse,
  provideHttpClient,
  withInterceptors,
} from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';

import { API_BASE_URL } from '../config/api.config';
import { authInterceptor } from './auth.interceptor';
import { CsrfTokenStore } from './csrf-token-store';

const CSRF_INVALID = { detail: 'CSRF inválido.' };
const CSRF_INVALID_OPTS = { status: 403, statusText: 'Forbidden' };

describe('authInterceptor', () => {
  let http: HttpClient;
  let httpMock: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(withInterceptors([authInterceptor])),
        provideHttpClientTesting(),
      ],
    });
    http = TestBed.inject(HttpClient);
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    httpMock.verify();
  });

  it("sources the CSRF token from GET /auth/csrf's response body and attaches it on POST", () => {
    // Deliberately no document.cookie set up anywhere in this spec: the
    // interceptor must never read it (AUTH-CSRF-CROSS-ORIGIN-001) — the
    // token can only come from the CsrfTokenStore, which itself only ever
    // reads it from the JSON body.
    http.post(`${API_BASE_URL}/auth/login`, {}).subscribe();

    const csrfReq = httpMock.expectOne(`${API_BASE_URL}/auth/csrf`);
    expect(csrfReq.request.method).toBe('GET');
    csrfReq.flush({ status: 'ok', csrf_token: 'body-sourced-token' });

    const loginReq = httpMock.expectOne(`${API_BASE_URL}/auth/login`);
    expect(loginReq.request.withCredentials).toBe(true);
    expect(loginReq.request.headers.get('X-CSRF-Token')).toBe('body-sourced-token');
    loginReq.flush({});
  });

  it('attaches withCredentials but no CSRF header, and fetches no token, on GET requests', () => {
    http.get(`${API_BASE_URL}/auth/me`).subscribe();

    const req = httpMock.expectOne(`${API_BASE_URL}/auth/me`);
    expect(req.request.withCredentials).toBe(true);
    expect(req.request.headers.has('X-CSRF-Token')).toBe(false);
    req.flush({});

    httpMock.expectNone(`${API_BASE_URL}/auth/csrf`);
  });

  it('does not touch requests outside the API base URL', () => {
    http.get('https://unrelated.example.test/data').subscribe();

    const req = httpMock.expectOne('https://unrelated.example.test/data');
    expect(req.request.withCredentials).toBe(false);
    expect(req.request.headers.has('X-CSRF-Token')).toBe(false);
    req.flush({});
  });

  it('reuses an already-primed token without an extra CSRF fetch on a later mutation', () => {
    http.post(`${API_BASE_URL}/auth/login`, {}).subscribe();
    httpMock
      .expectOne(`${API_BASE_URL}/auth/csrf`)
      .flush({ status: 'ok', csrf_token: 'primed-token' });
    httpMock.expectOne(`${API_BASE_URL}/auth/login`).flush({});

    http.post(`${API_BASE_URL}/auth/logout`, {}).subscribe();
    const logoutReq = httpMock.expectOne(`${API_BASE_URL}/auth/logout`);
    expect(logoutReq.request.headers.get('X-CSRF-Token')).toBe('primed-token');
    logoutReq.flush({});
  });

  it('dedupes concurrent mutations issued before the token resolves into a single CSRF fetch', () => {
    // Reproduces the exact race this task fixes: two mutating requests
    // fired back-to-back before any GET /auth/csrf has completed must not
    // each fire their own priming request, and neither may go out without
    // the header.
    http.post(`${API_BASE_URL}/auth/login`, {}).subscribe();
    http.post(`${API_BASE_URL}/auth/register`, {}).subscribe();

    const csrfReq = httpMock.expectOne(`${API_BASE_URL}/auth/csrf`);
    csrfReq.flush({ status: 'ok', csrf_token: 'shared-token' });

    const loginReq = httpMock.expectOne(`${API_BASE_URL}/auth/login`);
    const registerReq = httpMock.expectOne(`${API_BASE_URL}/auth/register`);
    expect(loginReq.request.headers.get('X-CSRF-Token')).toBe('shared-token');
    expect(registerReq.request.headers.get('X-CSRF-Token')).toBe('shared-token');
    loginReq.flush({});
    registerReq.flush({});
  });

  it('retries exactly once with a fresh token when a mutation is rejected as CSRF invalid', () => {
    // Reproduces an expired CSRF cookie/token mid-session: the first
    // attempt carries a token the backend no longer accepts.
    let succeeded = false;
    http.post(`${API_BASE_URL}/auth/login`, {}).subscribe(() => (succeeded = true));

    httpMock
      .expectOne(`${API_BASE_URL}/auth/csrf`)
      .flush({ status: 'ok', csrf_token: 'stale-token' });

    const firstAttempt = httpMock.expectOne(`${API_BASE_URL}/auth/login`);
    expect(firstAttempt.request.headers.get('X-CSRF-Token')).toBe('stale-token');
    firstAttempt.flush(CSRF_INVALID, CSRF_INVALID_OPTS);

    const renewal = httpMock.expectOne(`${API_BASE_URL}/auth/csrf`);
    renewal.flush({ status: 'ok', csrf_token: 'fresh-token' });

    const retryAttempt = httpMock.expectOne(`${API_BASE_URL}/auth/login`);
    expect(retryAttempt.request.headers.get('X-CSRF-Token')).toBe('fresh-token');
    retryAttempt.flush({ id: 'user-id', identifier: 'owner@example.test' });

    expect(succeeded).toBe(true);
  });

  it('propagates a second CSRF-invalid 403 without retrying again', () => {
    let receivedError: HttpErrorResponse | undefined;
    http
      .post(`${API_BASE_URL}/auth/login`, {})
      .subscribe({ error: (error: HttpErrorResponse) => (receivedError = error) });

    httpMock
      .expectOne(`${API_BASE_URL}/auth/csrf`)
      .flush({ status: 'ok', csrf_token: 'stale-token' });
    httpMock.expectOne(`${API_BASE_URL}/auth/login`).flush(CSRF_INVALID, CSRF_INVALID_OPTS);

    httpMock
      .expectOne(`${API_BASE_URL}/auth/csrf`)
      .flush({ status: 'ok', csrf_token: 'fresh-token' });
    // The retry also comes back CSRF-invalid: no third attempt, no third
    // CSRF fetch — the error is simply returned to the caller.
    httpMock.expectOne(`${API_BASE_URL}/auth/login`).flush(CSRF_INVALID, CSRF_INVALID_OPTS);

    expect(receivedError?.status).toBe(403);
    httpMock.expectNone(`${API_BASE_URL}/auth/csrf`);
    httpMock.expectNone(`${API_BASE_URL}/auth/login`);
  });

  it('does not retry a 403 that is not a CSRF failure', () => {
    let receivedError: HttpErrorResponse | undefined;
    http
      .post(`${API_BASE_URL}/auth/login`, {})
      .subscribe({ error: (error: HttpErrorResponse) => (receivedError = error) });

    httpMock.expectOne(`${API_BASE_URL}/auth/csrf`).flush({ status: 'ok', csrf_token: 'token' });
    httpMock
      .expectOne(`${API_BASE_URL}/auth/login`)
      .flush({ detail: 'Credenciales incorrectas.' }, { status: 403, statusText: 'Forbidden' });

    expect(receivedError?.status).toBe(403);
    expect(receivedError?.error?.detail).toBe('Credenciales incorrectas.');
    httpMock.expectNone(`${API_BASE_URL}/auth/csrf`);
  });

  it('fetches a fresh token for the next mutation after the store is cleared (e.g. by logout)', () => {
    // AuthService.logout() calls csrfStore.clear() directly — this
    // reproduces that effect without going through AuthService, since this
    // spec only wires up the interceptor.
    const csrfStore = TestBed.inject(CsrfTokenStore);

    http.post(`${API_BASE_URL}/auth/login`, {}).subscribe();
    httpMock
      .expectOne(`${API_BASE_URL}/auth/csrf`)
      .flush({ status: 'ok', csrf_token: 'pre-logout-token' });
    httpMock.expectOne(`${API_BASE_URL}/auth/login`).flush({});

    csrfStore.clear();

    http.post(`${API_BASE_URL}/auth/login`, {}).subscribe();
    httpMock
      .expectOne(`${API_BASE_URL}/auth/csrf`)
      .flush({ status: 'ok', csrf_token: 'post-logout-token' });
    const secondLoginReq = httpMock.expectOne(`${API_BASE_URL}/auth/login`);
    expect(secondLoginReq.request.headers.get('X-CSRF-Token')).toBe('post-logout-token');
    secondLoginReq.flush({});
  });
});
