import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';

import { API_BASE_URL } from '../config/api.config';
import { CsrfTokenStore } from './csrf-token-store';

describe('CsrfTokenStore', () => {
  let store: CsrfTokenStore;
  let httpMock: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    store = TestBed.inject(CsrfTokenStore);
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    httpMock.verify();
  });

  it('fetches the token from GET /auth/csrf on first call', () => {
    let resolved: string | undefined;
    store.ensureToken().subscribe((token) => (resolved = token));

    const req = httpMock.expectOne(`${API_BASE_URL}/auth/csrf`);
    expect(req.request.method).toBe('GET');
    req.flush({ status: 'ok', csrf_token: 'first-token' });

    expect(resolved).toBe('first-token');
  });

  it('caches the token in memory and does not re-fetch on a later call', () => {
    store.ensureToken().subscribe();
    httpMock
      .expectOne(`${API_BASE_URL}/auth/csrf`)
      .flush({ status: 'ok', csrf_token: 'cached-token' });

    let secondResolved: string | undefined;
    store.ensureToken().subscribe((token) => (secondResolved = token));

    httpMock.expectNone(`${API_BASE_URL}/auth/csrf`);
    expect(secondResolved).toBe('cached-token');
  });

  it('dedupes concurrent calls before the first response arrives into one HTTP request', () => {
    const results: string[] = [];
    store.ensureToken().subscribe((token) => results.push(token));
    store.ensureToken().subscribe((token) => results.push(token));

    const req = httpMock.expectOne(`${API_BASE_URL}/auth/csrf`);
    req.flush({ status: 'ok', csrf_token: 'shared-token' });

    expect(results).toEqual(['shared-token', 'shared-token']);
  });

  it('allows a fresh fetch on a later call after a failed one', () => {
    store.ensureToken().subscribe({ error: () => undefined });
    httpMock.expectOne(`${API_BASE_URL}/auth/csrf`).error(new ProgressEvent('network error'));

    let resolved: string | undefined;
    store.ensureToken().subscribe((token) => (resolved = token));
    httpMock
      .expectOne(`${API_BASE_URL}/auth/csrf`)
      .flush({ status: 'ok', csrf_token: 'retry-token' });

    expect(resolved).toBe('retry-token');
  });

  it('rejects and does not cache an empty csrf_token', () => {
    let receivedError: unknown;
    store.ensureToken().subscribe({ error: (error: unknown) => (receivedError = error) });
    httpMock.expectOne(`${API_BASE_URL}/auth/csrf`).flush({ status: 'ok', csrf_token: '' });

    expect(receivedError).toBeDefined();

    // Not cached: a later call fetches again instead of resolving an
    // empty string from memory.
    let resolved: string | undefined;
    store.ensureToken().subscribe((token) => (resolved = token));
    httpMock
      .expectOne(`${API_BASE_URL}/auth/csrf`)
      .flush({ status: 'ok', csrf_token: 'valid-token' });

    expect(resolved).toBe('valid-token');
  });

  it('never stores the token in localStorage or sessionStorage', () => {
    store.ensureToken().subscribe();
    httpMock
      .expectOne(`${API_BASE_URL}/auth/csrf`)
      .flush({ status: 'ok', csrf_token: 'memory-only-token' });

    expect(JSON.stringify(localStorage)).not.toContain('memory-only-token');
    expect(JSON.stringify(sessionStorage)).not.toContain('memory-only-token');
  });
});
