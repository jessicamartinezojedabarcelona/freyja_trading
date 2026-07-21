import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';

import { API_BASE_URL } from '../config/api.config';
import { AuthService } from './auth.service';

describe('AuthService', () => {
  let service: AuthService;
  let httpMock: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    service = TestBed.inject(AuthService);
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    httpMock.verify();
  });

  it('starts with no current user', () => {
    expect(service.currentUser()).toBeNull();
  });

  it('login() sets the current user on success', () => {
    service.login('owner@example.test', 'correct-horse-battery-staple').subscribe();

    const req = httpMock.expectOne(`${API_BASE_URL}/auth/login`);
    expect(req.request.method).toBe('POST');
    req.flush({ id: 'user-id', identifier: 'owner@example.test' });

    expect(service.currentUser()).toEqual({ id: 'user-id', identifier: 'owner@example.test' });
  });

  it('primeCsrf() issues a GET to /auth/csrf and does not touch currentUser', () => {
    service.primeCsrf().subscribe();

    const req = httpMock.expectOne(`${API_BASE_URL}/auth/csrf`);
    expect(req.request.method).toBe('GET');
    req.flush({ status: 'ok' });

    expect(service.currentUser()).toBeNull();
  });

  it('me() sets the current user on success', () => {
    service.me().subscribe();

    const req = httpMock.expectOne(`${API_BASE_URL}/auth/me`);
    expect(req.request.method).toBe('GET');
    req.flush({ id: 'user-id', identifier: 'owner@example.test' });

    expect(service.currentUser()).toEqual({ id: 'user-id', identifier: 'owner@example.test' });
  });

  it('logout() clears the current user', () => {
    service.login('owner@example.test', 'correct-horse-battery-staple').subscribe();
    httpMock
      .expectOne(`${API_BASE_URL}/auth/login`)
      .flush({ id: 'user-id', identifier: 'owner@example.test' });

    service.logout().subscribe();
    const req = httpMock.expectOne(`${API_BASE_URL}/auth/logout`);
    expect(req.request.method).toBe('POST');
    req.flush(null);

    expect(service.currentUser()).toBeNull();
  });

  it('register() posts email and password', () => {
    service.register('newuser@example.test', 'a-strong-password-123').subscribe();

    const req = httpMock.expectOne(`${API_BASE_URL}/auth/register`);
    expect(req.request.method).toBe('POST');
    expect(req.request.body).toEqual({
      email: 'newuser@example.test',
      password: 'a-strong-password-123',
    });
    req.flush({ status: 'ok' });
  });

  it('forgotPassword() posts the email', () => {
    service.forgotPassword('someone@example.test').subscribe();

    const req = httpMock.expectOne(`${API_BASE_URL}/auth/forgot-password`);
    expect(req.request.method).toBe('POST');
    expect(req.request.body).toEqual({ email: 'someone@example.test' });
    req.flush({ status: 'ok' });
  });

  it('resetPassword() posts the token and new password with a snake_case key', () => {
    service.resetPassword('a-token', 'a-new-strong-password').subscribe();

    const req = httpMock.expectOne(`${API_BASE_URL}/auth/reset-password`);
    expect(req.request.method).toBe('POST');
    expect(req.request.body).toEqual({
      token: 'a-token',
      new_password: 'a-new-strong-password',
    });
    req.flush({ status: 'ok' });
  });
});
