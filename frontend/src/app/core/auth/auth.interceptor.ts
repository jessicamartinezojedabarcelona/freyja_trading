import { HttpInterceptorFn } from '@angular/common/http';
import { inject } from '@angular/core';
import { switchMap } from 'rxjs';

import { API_BASE_URL } from '../config/api.config';
import { CsrfTokenStore } from './csrf-token-store';

const CSRF_HEADER_NAME = 'X-CSRF-Token';
const STATE_CHANGING_METHODS = new Set(['POST', 'PUT', 'PATCH', 'DELETE']);

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
  return csrfStore
    .ensureToken()
    .pipe(
      switchMap((token) => next(outgoing.clone({ setHeaders: { [CSRF_HEADER_NAME]: token } }))),
    );
};
