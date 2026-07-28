import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable, finalize, map, of, shareReplay } from 'rxjs';

import { API_BASE_URL } from '../config/api.config';
import { CsrfTokenResponse } from './auth.models';

/**
 * Holds the CSRF token only in memory (never localStorage, sessionStorage,
 * or any other persisted store) — the frontend cannot read the backend's
 * host-only freyja_csrf cookie via document.cookie once frontend and
 * backend live on different origins (AUTH-CSRF-CROSS-ORIGIN-001), so the
 * token returned in GET /auth/csrf's response body is the only source of
 * truth the interceptor can use.
 */
@Injectable({ providedIn: 'root' })
export class CsrfTokenStore {
  private readonly http = inject(HttpClient);

  private token: string | null = null;
  private inFlight$: Observable<string> | null = null;

  /**
   * Resolves to the current token, fetching it if necessary. Concurrent
   * callers before the first response arrives share the same in-flight
   * request instead of each firing their own GET /auth/csrf.
   */
  ensureToken(): Observable<string> {
    if (this.token) {
      return of(this.token);
    }

    return this.fetchToken();
  }

  /**
   * Atomically invalidates the cached token and fetches a fresh one — used
   * when a request comes back rejected as CSRF-invalid (a stale cookie, or
   * one from before a logout). Deliberately routes through the same
   * inFlight$ guard as ensureToken(): if two mutations are rejected around
   * the same time, both call refreshToken(), but only the first actually
   * starts a GET /auth/csrf — the second reuses that same in-flight
   * Observable instead of firing a second concurrent renewal, which would
   * otherwise leave the two mutations retrying with mismatched
   * cookie/token pairs.
   */
  refreshToken(): Observable<string> {
    this.token = null;
    return this.fetchToken();
  }

  clear(): void {
    this.token = null;
    this.inFlight$ = null;
  }

  private fetchToken(): Observable<string> {
    if (!this.inFlight$) {
      this.inFlight$ = this.http.get<CsrfTokenResponse>(`${API_BASE_URL}/auth/csrf`).pipe(
        map((response) => {
          if (!response.csrf_token) {
            throw new Error('GET /auth/csrf devolvió un csrf_token vacío.');
          }
          this.token = response.csrf_token;
          return response.csrf_token;
        }),
        // Resets on both success and failure — a resolved fetch has
        // already cached its token on `this.token` (so ensureToken()'s
        // fast path takes over), and a failed one must not leave a dead
        // in-flight reference blocking the next real attempt.
        finalize(() => {
          this.inFlight$ = null;
        }),
        shareReplay(1),
      );
    }

    return this.inFlight$;
  }
}
