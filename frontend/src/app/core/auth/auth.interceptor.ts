import { HttpInterceptorFn } from '@angular/common/http';

import { API_BASE_URL } from '../config/api.config';

const CSRF_COOKIE_NAME = 'freyja_csrf';
const CSRF_HEADER_NAME = 'X-CSRF-Token';
const STATE_CHANGING_METHODS = new Set(['POST', 'PUT', 'PATCH', 'DELETE']);

function readCookie(name: string): string | null {
  const match = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`));
  return match ? decodeURIComponent(match[1]) : null;
}

export const authInterceptor: HttpInterceptorFn = (req, next) => {
  if (!req.url.startsWith(API_BASE_URL)) {
    return next(req);
  }

  let outgoing = req.clone({ withCredentials: true });

  if (STATE_CHANGING_METHODS.has(req.method)) {
    const csrfToken = readCookie(CSRF_COOKIE_NAME);
    if (csrfToken) {
      outgoing = outgoing.clone({ setHeaders: { [CSRF_HEADER_NAME]: csrfToken } });
    }
  }

  return next(outgoing);
};
