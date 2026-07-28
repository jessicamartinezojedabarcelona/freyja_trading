import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable, catchError, map, of, shareReplay, throwError } from 'rxjs';

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

    if (!this.inFlight$) {
      this.inFlight$ = this.http.get<CsrfTokenResponse>(`${API_BASE_URL}/auth/csrf`).pipe(
        map((response) => {
          this.token = response.csrf_token;
          return response.csrf_token;
        }),
        catchError((error: unknown) => {
          this.inFlight$ = null;
          return throwError(() => error);
        }),
        shareReplay(1),
      );
    }

    return this.inFlight$;
  }

  clear(): void {
    this.token = null;
    this.inFlight$ = null;
  }
}
