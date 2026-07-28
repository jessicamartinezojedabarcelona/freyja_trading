import { HttpClient, provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';

import { API_BASE_URL } from '../config/api.config';
import { authInterceptor } from './auth.interceptor';

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
});
