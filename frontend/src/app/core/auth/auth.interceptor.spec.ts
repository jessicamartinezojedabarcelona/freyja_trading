import { HttpClient, provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';

import { API_BASE_URL } from '../config/api.config';
import { authInterceptor } from './auth.interceptor';

describe('authInterceptor', () => {
  let http: HttpClient;
  let httpMock: HttpTestingController;

  beforeEach(() => {
    document.cookie = 'freyja_csrf=test-csrf-token; path=/';

    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(withInterceptors([authInterceptor])),
        provideHttpClientTesting(),
      ],
    });
    http = TestBed.inject(HttpClient);
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    httpMock.verify();
    document.cookie = 'freyja_csrf=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT';
  });

  it('attaches withCredentials and the CSRF header on POST requests to the API', () => {
    http.post(`${API_BASE_URL}/auth/login`, {}).subscribe();

    const req = httpMock.expectOne(`${API_BASE_URL}/auth/login`);
    expect(req.request.withCredentials).toBe(true);
    expect(req.request.headers.get('X-CSRF-Token')).toBe('test-csrf-token');
    req.flush({});
  });

  it('attaches withCredentials but no CSRF header on GET requests to the API', () => {
    http.get(`${API_BASE_URL}/auth/me`).subscribe();

    const req = httpMock.expectOne(`${API_BASE_URL}/auth/me`);
    expect(req.request.withCredentials).toBe(true);
    expect(req.request.headers.has('X-CSRF-Token')).toBe(false);
    req.flush({});
  });

  it('does not touch requests outside the API base URL', () => {
    http.get('https://unrelated.example.test/data').subscribe();

    const req = httpMock.expectOne('https://unrelated.example.test/data');
    expect(req.request.withCredentials).toBe(false);
    expect(req.request.headers.has('X-CSRF-Token')).toBe(false);
    req.flush({});
  });
});
