import { HttpClient } from '@angular/common/http';
import { Injectable, inject, signal } from '@angular/core';
import { Observable, tap } from 'rxjs';

import { API_BASE_URL } from '../config/api.config';
import { AuthUser, StatusResponse } from './auth.models';

@Injectable({ providedIn: 'root' })
export class AuthService {
  private readonly http = inject(HttpClient);
  private readonly currentUserSignal = signal<AuthUser | null>(null);

  readonly currentUser = this.currentUserSignal.asReadonly();

  /** Single-responsibility CSRF priming: issues/renews the freyja_csrf
   * cookie. Creates no session and returns no user data — safe to call from
   * a fully anonymous, cookie-less browser on first load. */
  primeCsrf(): Observable<StatusResponse> {
    return this.http.get<StatusResponse>(`${API_BASE_URL}/auth/csrf`);
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
