import { HttpErrorResponse, provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';

import { API_BASE_URL } from '../../core/config/api.config';
import { ForgotPasswordPage } from './forgot-password.page';

describe('ForgotPasswordPage', () => {
  let httpMock: HttpTestingController;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [ForgotPasswordPage],
      providers: [provideRouter([]), provideHttpClient(), provideHttpClientTesting()],
    }).compileComponents();

    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    httpMock.verify();
  });

  it('shows the same generic acknowledgement whether the account exists or not', () => {
    const fixture = TestBed.createComponent(ForgotPasswordPage);
    const component = fixture.componentInstance;

    component.form.setValue({ email: 'someone@example.test' });
    component.submit();

    httpMock.expectOne(`${API_BASE_URL}/auth/forgot-password`).flush({ status: 'ok' });

    expect(component.submitted()).toBe(true);
  });

  it('shows the same generic acknowledgement even if the request fails', () => {
    const fixture = TestBed.createComponent(ForgotPasswordPage);
    const component = fixture.componentInstance;

    component.form.setValue({ email: 'someone@example.test' });
    component.submit();

    httpMock
      .expectOne(`${API_BASE_URL}/auth/forgot-password`)
      .flush(
        { detail: 'error' },
        new HttpErrorResponse({ status: 500, statusText: 'Internal Server Error' }),
      );

    expect(component.submitted()).toBe(true);
  });

  it('does not disable the submit button merely for being invalid', () => {
    const fixture = TestBed.createComponent(ForgotPasswordPage);
    fixture.detectChanges();
    const button = fixture.nativeElement.querySelector(
      'button[type="submit"]',
    ) as HTMLButtonElement;
    expect(button.disabled).toBe(false);
  });

  it('does not show a field error before any interaction', () => {
    const fixture = TestBed.createComponent(ForgotPasswordPage);
    fixture.detectChanges();
    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.querySelector('#email-error')).toBeNull();
    expect(compiled.querySelector('#email')?.getAttribute('aria-invalid')).toBeNull();
  });

  it('shows a textual error, wires aria-invalid/aria-describedby, and focuses the field on an invalid submit attempt', () => {
    const fixture = TestBed.createComponent(ForgotPasswordPage);
    fixture.detectChanges();
    const compiled = fixture.nativeElement as HTMLElement;

    (compiled.querySelector('form') as HTMLFormElement).requestSubmit();
    fixture.detectChanges();

    const emailInput = compiled.querySelector('#email') as HTMLInputElement;
    const emailError = compiled.querySelector('#email-error') as HTMLElement;
    expect(emailInput.getAttribute('aria-invalid')).toBe('true');
    expect(emailInput.getAttribute('aria-describedby')).toBe('email-error');
    expect(emailError.textContent).toContain('Introduce tu correo');
    expect(document.activeElement).toBe(emailInput);
  });
});
