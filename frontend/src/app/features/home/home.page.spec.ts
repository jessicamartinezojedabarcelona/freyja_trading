import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { Router, provideRouter } from '@angular/router';

import { API_BASE_URL } from '../../core/config/api.config';
import { AuthService } from '../../core/auth/auth.service';
import { HomePage } from './home.page';

describe('HomePage', () => {
  let httpMock: HttpTestingController;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [HomePage],
      providers: [provideRouter([]), provideHttpClient(), provideHttpClientTesting()],
    }).compileComponents();

    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    httpMock.verify();
  });

  it('shows the identifier of the current user once resolved', () => {
    const authService = TestBed.inject(AuthService);
    authService.me().subscribe();
    httpMock
      .expectOne(`${API_BASE_URL}/auth/me`)
      .flush({ id: 'user-id', identifier: 'owner@example.test' });

    const fixture = TestBed.createComponent(HomePage);
    fixture.detectChanges();
    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.textContent).toContain('owner@example.test');
  });

  it('navigates to /login after logout', () => {
    const fixture = TestBed.createComponent(HomePage);
    const router = TestBed.inject(Router);
    const navigateSpy = vi.spyOn(router, 'navigateByUrl').mockResolvedValue(true);

    fixture.componentInstance.logout();

    httpMock.expectOne(`${API_BASE_URL}/auth/logout`).flush(null);

    expect(navigateSpy).toHaveBeenCalledWith('/login');
  });
});
