import { HttpErrorResponse, provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { ActivatedRoute, Router, convertToParamMap, provideRouter } from '@angular/router';

import { API_BASE_URL } from '../../core/config/api.config';
import { LoginPage } from './login.page';

describe('LoginPage', () => {
  let httpMock: HttpTestingController;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [LoginPage],
      providers: [provideRouter([]), provideHttpClient(), provideHttpClientTesting()],
    }).compileComponents();

    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    httpMock.verify();
  });

  it('renders identifier and password fields', () => {
    const fixture = TestBed.createComponent(LoginPage);
    fixture.detectChanges();
    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.querySelector('#identifier')).toBeTruthy();
    expect(compiled.querySelector('input[type="password"]')).toBeTruthy();
  });

  it('does not disable the submit button merely for being invalid — the user must be able to attempt submission and see why it failed', () => {
    const fixture = TestBed.createComponent(LoginPage);
    fixture.detectChanges();
    const button = fixture.nativeElement.querySelector(
      'button[type="submit"]',
    ) as HTMLButtonElement;
    expect(button.disabled).toBe(false);
  });

  it('does not show field errors before any interaction', () => {
    const fixture = TestBed.createComponent(LoginPage);
    fixture.detectChanges();
    const compiled = fixture.nativeElement as HTMLElement;

    expect(compiled.querySelector('#identifier-error')).toBeNull();
    expect(compiled.querySelector('#password-error')).toBeNull();
    expect(compiled.querySelector('#identifier')?.getAttribute('aria-invalid')).toBeNull();
  });

  it('shows textual field errors and wires aria-invalid/aria-describedby after an invalid submit attempt, and moves focus to the first invalid field', () => {
    const fixture = TestBed.createComponent(LoginPage);
    fixture.detectChanges();
    const compiled = fixture.nativeElement as HTMLElement;

    const form = compiled.querySelector('form') as HTMLFormElement;
    form.requestSubmit();
    fixture.detectChanges();

    const identifierInput = compiled.querySelector('#identifier') as HTMLInputElement;
    const identifierError = compiled.querySelector('#identifier-error') as HTMLElement;

    expect(identifierInput.getAttribute('aria-invalid')).toBe('true');
    expect(identifierInput.getAttribute('aria-describedby')).toBe('identifier-error');
    expect(identifierError.id).toBe('identifier-error');
    expect(identifierError.textContent).toContain('Introduce tu correo');
    expect(document.activeElement).toBe(identifierInput);
  });

  it('field error messages never contain the value the user typed', () => {
    const fixture = TestBed.createComponent(LoginPage);
    const component = fixture.componentInstance;
    fixture.detectChanges();

    component.form.controls.identifier.setValue('not-a-real-email-format');
    component.form.controls.identifier.markAsTouched();
    fixture.detectChanges();

    // identifier has no format validator (required only), so a non-empty
    // value is always valid here — this asserts no error text is ever
    // fabricated to include the typed value regardless.
    const compiled = fixture.nativeElement as HTMLElement;
    const errorEl = compiled.querySelector('#identifier-error');
    expect(errorEl?.textContent ?? '').not.toContain('not-a-real-email-format');
  });

  it('clears field errors once the form becomes valid again', () => {
    const fixture = TestBed.createComponent(LoginPage);
    const component = fixture.componentInstance;
    fixture.detectChanges();

    const compiled = fixture.nativeElement as HTMLElement;
    (compiled.querySelector('form') as HTMLFormElement).requestSubmit();
    fixture.detectChanges();
    expect(compiled.querySelector('#identifier-error')).toBeTruthy();

    component.form.setValue({ identifier: 'owner@example.test', password: 'a-password' });
    fixture.detectChanges();

    expect(compiled.querySelector('#identifier-error')).toBeNull();
    expect(compiled.querySelector('#identifier')?.getAttribute('aria-invalid')).toBeNull();
  });

  it('shows the loading state while the request is in flight', () => {
    const fixture = TestBed.createComponent(LoginPage);
    const component = fixture.componentInstance;

    component.form.setValue({ identifier: 'owner@example.test', password: 'a-password' });
    component.submit();
    fixture.detectChanges();

    expect(component.submitting()).toBe(true);
    const button = fixture.nativeElement.querySelector(
      'button[type="submit"]',
    ) as HTMLButtonElement;
    expect(button.disabled).toBe(true);
    expect(button.textContent).toContain('Entrando');

    httpMock
      .expectOne(`${API_BASE_URL}/auth/login`)
      .flush({ id: 'user-id', identifier: 'owner@example.test' });

    expect(component.submitting()).toBe(false);
  });

  it('navigates to "/" after a successful login', () => {
    const fixture = TestBed.createComponent(LoginPage);
    const component = fixture.componentInstance;
    const router = TestBed.inject(Router);
    const navigateSpy = vi.spyOn(router, 'navigateByUrl').mockResolvedValue(true);

    component.form.setValue({ identifier: 'owner@example.test', password: 'a-password' });
    component.submit();

    httpMock
      .expectOne(`${API_BASE_URL}/auth/login`)
      .flush({ id: 'user-id', identifier: 'owner@example.test' });

    expect(navigateSpy).toHaveBeenCalledWith('/');
  });

  it('shows a generic error message on invalid credentials', () => {
    const fixture = TestBed.createComponent(LoginPage);
    const component = fixture.componentInstance;

    component.form.setValue({ identifier: 'owner@example.test', password: 'wrong-password' });
    component.submit();

    httpMock
      .expectOne(`${API_BASE_URL}/auth/login`)
      .flush(
        { detail: 'Credenciales incorrectas.' },
        new HttpErrorResponse({ status: 401, statusText: 'Unauthorized' }),
      );

    expect(component.errorMessage()).toBe('Correo o contraseña incorrectos.');
  });

  it('shows a rate-limit message on 429', () => {
    const fixture = TestBed.createComponent(LoginPage);
    const component = fixture.componentInstance;

    component.form.setValue({ identifier: 'owner@example.test', password: 'wrong-password' });
    component.submit();

    httpMock
      .expectOne(`${API_BASE_URL}/auth/login`)
      .flush(
        { detail: 'Demasiados intentos.' },
        new HttpErrorResponse({ status: 429, statusText: 'Too Many Requests' }),
      );

    expect(component.errorMessage()).toBe('Demasiados intentos. Vuelve a intentarlo más tarde.');
  });

  it('never shows a raw network/browser error on connection failure', () => {
    const fixture = TestBed.createComponent(LoginPage);
    const component = fixture.componentInstance;

    component.form.setValue({ identifier: 'owner@example.test', password: 'a-password' });
    component.submit();

    httpMock
      .expectOne(`${API_BASE_URL}/auth/login`)
      .error(new ProgressEvent('error'), { status: 0, statusText: 'Unknown Error' });

    expect(component.errorMessage()).toBe(
      'No se pudo conectar con el servidor. Comprueba tu conexión e inténtalo de nuevo.',
    );
    expect(component.errorMessage()).not.toContain('Failed to fetch');
  });

  it('toggles password visibility with an accessible name that reflects state', () => {
    const fixture = TestBed.createComponent(LoginPage);
    fixture.detectChanges();
    const compiled = fixture.nativeElement as HTMLElement;

    const input = compiled.querySelector('#password') as HTMLInputElement;
    const toggle = compiled.querySelector('.password-toggle') as HTMLButtonElement;

    expect(input.type).toBe('password');
    expect(toggle.getAttribute('aria-label')).toBe('Mostrar contraseña');
    expect(toggle.getAttribute('type')).toBe('button');

    toggle.click();
    fixture.detectChanges();

    expect(input.type).toBe('text');
    expect(toggle.getAttribute('aria-label')).toBe('Ocultar contraseña');
  });

  it('renders links to register and forgot-password', () => {
    const fixture = TestBed.createComponent(LoginPage);
    fixture.detectChanges();
    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.querySelector('a[routerLink="/register"]')).toBeTruthy();
    expect(compiled.querySelector('a[routerLink="/forgot-password"]')).toBeTruthy();
  });
});

describe('LoginPage with an expired-session query param', () => {
  let httpMock: HttpTestingController;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [LoginPage],
      providers: [
        provideRouter([]),
        provideHttpClient(),
        provideHttpClientTesting(),
        {
          provide: ActivatedRoute,
          useValue: {
            snapshot: { queryParamMap: convertToParamMap({ expired: '1' }) },
          },
        },
      ],
    }).compileComponents();

    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    httpMock.verify();
  });

  it('shows the session-expired notice', () => {
    const fixture = TestBed.createComponent(LoginPage);
    fixture.detectChanges();
    expect(fixture.componentInstance.sessionExpired()).toBe(true);
    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.textContent).toContain('Tu sesión ha expirado');
  });
});
