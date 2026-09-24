import { HttpErrorResponse, HttpInterceptorFn } from '@angular/common/http';
import { inject } from '@angular/core';
import { Router } from '@angular/router';
import { catchError, throwError } from 'rxjs';

import { API_BASE_URL } from '../config/api.config';
import { AuthService } from './auth.service';

/** When the server answers 401 to a request made with a session, the session has
 * expired or been revoked: forget it and go to the login screen, with the
 * "your session expired" notice. Whatever screen was open no longer shows an
 * unexplained generic error.
 *
 * The /auth/ endpoints are left alone: there, 401 is an ordinary answer (wrong
 * credentials, no session yet) that each screen already explains itself. */
export const sessionExpiredInterceptor: HttpInterceptorFn = (req, next) => {
  const authService = inject(AuthService);
  const router = inject(Router);

  return next(req).pipe(
    catchError((error: unknown) => {
      const isApiCall = req.url.startsWith(API_BASE_URL);
      const isAuthCall = req.url.startsWith(`${API_BASE_URL}/auth/`);
      if (isApiCall && !isAuthCall && error instanceof HttpErrorResponse && error.status === 401) {
        const hadSession = authService.currentUser() !== null;
        authService.clearSession();
        void router.navigate(['/login'], { queryParams: hadSession ? { expired: '1' } : {} });
      }
      return throwError(() => error);
    }),
  );
};
