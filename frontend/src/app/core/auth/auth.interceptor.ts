import { HttpErrorResponse, HttpInterceptorFn } from '@angular/common/http';
import { inject } from '@angular/core';
import { catchError, switchMap, throwError } from 'rxjs';

import { API_BASE_URL } from '../config/api.config';
import { CsrfTokenStore } from './csrf-token-store';

const CSRF_HEADER_NAME = 'X-CSRF-Token';
const CSRF_INVALID_DETAIL = 'CSRF inválido.';
const STATE_CHANGING_METHODS = new Set(['POST', 'PUT', 'PATCH', 'DELETE']);

function isCsrfInvalidResponse(error: unknown): error is HttpErrorResponse {
  return (
    error instanceof HttpErrorResponse &&
    error.status === 403 &&
    (error.error as { detail?: unknown } | null)?.detail === CSRF_INVALID_DETAIL
  );
}

export const authInterceptor: HttpInterceptorFn = (req, next) => {
  if (!req.url.startsWith(API_BASE_URL)) {
    return next(req);
  }

  const outgoing = req.clone({ withCredentials: true });

  if (!STATE_CHANGING_METHODS.has(req.method)) {
    return next(outgoing);
  }

  // Never reads document.cookie: the freyja_csrf cookie is host-only on the
  // backend's origin and unreadable from the frontend's own (different)
  // origin in production. The store resolves the token from GET
  // /auth/csrf's response body instead, fetching it first if no request has
  // primed it yet — this is what eliminates the fire-and-forget race that
  // used to let a mutation go out before the token existed.
  const csrfStore = inject(CsrfTokenStore);
  const sendWithToken = (token: string) =>
    next(outgoing.clone({ setHeaders: { [CSRF_HEADER_NAME]: token } }));

  return csrfStore.ensureToken().pipe(
    switchMap((token) =>
      sendWithToken(token).pipe(
        catchError((error: unknown) => {
          if (!isCsrfInvalidResponse(error)) {
            return throwError(() => error);
          }
          // The CSRF cookie/token can go stale mid-session (expiry, or a
          // logout this same browser tab missed clearing). refreshToken()
          // atomically invalidates the cache and fetches exactly one fresh
          // token — if another mutation was rejected around the same time
          // and is also calling refreshToken(), both share the single
          // in-flight renewal instead of each starting their own, so they
          // never end up retrying with mismatched cookie/token pairs. No
          // catchError wraps this second attempt: a repeat CSRF-invalid
          // response propagates as-is rather than retrying again.
          return csrfStore
            .refreshToken()
            .pipe(switchMap((freshToken) => sendWithToken(freshToken)));
        }),
      ),
    ),
  );
};
