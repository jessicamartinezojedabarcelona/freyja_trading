import { HttpClient } from '@angular/common/http';
import { Injectable, inject, signal } from '@angular/core';
import { Observable, tap } from 'rxjs';

import { API_BASE_URL } from '../config/api.config';
import { AuthUser, StatusResponse } from './auth.models';
import { CsrfTokenStore } from './csrf-token-store';

@Injectable({ providedIn: 'root' })
export class AuthService {
  private readonly http = inject(HttpClient);
  private readonly csrfStore = inject(CsrfTokenStore);
  private readonly currentUserSignal = signal<AuthUser | null>(null);

  readonly currentUser = this.currentUserSignal.asReadonly();

  /** Single-responsibility CSRF priming: issues/renews the freyja_csrf
   * cookie and stores the token in memory via CsrfTokenStore. Creates no
   * session and returns no user data — safe to call from a fully
   * anonymous, cookie-less browser on first load. Harmless to call more
   * than once: the store dedupes concurrent fetches and caches the
   * result, so this is purely an optimization — the interceptor's own
   * ensureToken() call is what actually guarantees no mutation is sent
   * before a token exists. */
  primeCsrf(): Observable<string> {
    return this.csrfStore.ensureToken();
  }

  login(identifier: string, password: string): Observable<AuthUser> {
    return this.http
      .post<AuthUser>(`${API_BASE_URL}/auth/login`, { identifier, password })
      .pipe(tap((user) => this.currentUserSignal.set(user)));
  }

  logout(): Observable<void> {
    return this.http
      .post<void>(`${API_BASE_URL}/auth/logout`, {})
      .pipe(tap(() => this.currentUserSignal.set(null)));
  }

  me(): Observable<AuthUser> {
    return this.http
      .get<AuthUser>(`${API_BASE_URL}/auth/me`)
      .pipe(tap((user) => this.currentUserSignal.set(user)));
  }

  register(email: string, password: string): Observable<StatusResponse> {
    return this.http.post<StatusResponse>(`${API_BASE_URL}/auth/register`, { email, password });
  }

  forgotPassword(email: string): Observable<StatusResponse> {
    return this.http.post<StatusResponse>(`${API_BASE_URL}/auth/forgot-password`, { email });
  }

  resetPassword(token: string, newPassword: string): Observable<StatusResponse> {
    return this.http.post<StatusResponse>(`${API_BASE_URL}/auth/reset-password`, {
      token,
      new_password: newPassword,
    });
  }
}
