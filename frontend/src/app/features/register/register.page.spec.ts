import { HttpErrorResponse, provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';

import { API_BASE_URL } from '../../core/config/api.config';
import { RegisterPage } from './register.page';

const VALID_PASSWORD = 'a-strong-password-123';

describe('RegisterPage', () => {
  let httpMock: HttpTestingController;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [RegisterPage],
      providers: [provideRouter([]), provideHttpClient(), provideHttpClientTesting()],
    }).compileComponents();

    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    httpMock.verify();
  });

  it('renders email, password, and confirm-password fields', () => {
    const fixture = TestBed.createComponent(RegisterPage);
    fixture.detectChanges();
    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.querySelector('#email')).toBeTruthy();
    expect(compiled.querySelector('#password')).toBeTruthy();
    expect(compiled.querySelector('#confirmPassword')).toBeTruthy();
  });

  it('does not disable the submit button merely for being invalid — the user must be able to attempt submission and see why it failed', () => {
    const fixture = TestBed.createComponent(RegisterPage);
    fixture.detectChanges();
    const button = fixture.nativeElement.querySelector(
      'button[type="submit"]',
    ) as HTMLButtonElement;
    expect(button.disabled).toBe(false);
  });

  it('does not show field errors before any interaction', () => {
    const fixture = TestBed.createComponent(RegisterPage);
    fixture.detectChanges();
    const compiled = fixture.nativeElement as HTMLElement;

    expect(compiled.querySelector('#email-error')).toBeNull();
    expect(compiled.querySelector('#password-error')).toBeNull();
    expect(compiled.querySelector('#confirmPassword-error')).toBeNull();
    expect(compiled.querySelector('#email')?.getAttribute('aria-invalid')).toBeNull();
    expect(compiled.querySelector('#confirmPassword')?.getAttribute('aria-invalid')).toBeNull();
  });

  it('shows a specific email-format error distinct from the empty-field error, wired via aria-describedby', () => {
    const fixture = TestBed.createComponent(RegisterPage);
    const component = fixture.componentInstance;
    fixture.detectChanges();
    const compiled = fixture.nativeElement as HTMLElement;

    component.form.controls.email.setValue('not-an-email');
    component.form.controls.email.markAsTouched();
    fixture.detectChanges();

    const emailInput = compiled.querySelector('#email') as HTMLInputElement;
    const emailError = compiled.querySelector('#email-error') as HTMLElement;
    expect(emailInput.getAttribute('aria-invalid')).toBe('true');
    expect(emailInput.getAttribute('aria-describedby')).toBe('email-error');
    expect(emailError.textContent).toContain('formato del correo no es válido');
    expect(emailError.textContent).not.toContain('not-an-email');
  });

  it('references both the persistent hint and the error via aria-describedby on the password field', () => {
    const fixture = TestBed.createComponent(RegisterPage);
    const component = fixture.componentInstance;
    fixture.detectChanges();
    const compiled = fixture.nativeElement as HTMLElement;

    const passwordInput = compiled.querySelector('#password') as HTMLInputElement;
    expect(passwordInput.getAttribute('aria-describedby')).toBe('password-hint');
    expect(compiled.querySelector('#password-hint')?.textContent).toContain('12 caracteres');

    component.form.controls.password.setValue('short');
    component.form.controls.password.markAsTouched();
    fixture.detectChanges();

    expect(passwordInput.getAttribute('aria-describedby')).toBe('password-hint password-error');
    expect(compiled.querySelector('#password-error')?.textContent).toContain(
      'al menos 12 caracteres',
    );
  });

  it('moves focus to the first invalid field (email) on an invalid submit attempt', () => {
    const fixture = TestBed.createComponent(RegisterPage);
    fixture.detectChanges();
    const compiled = fixture.nativeElement as HTMLElement;

    (compiled.querySelector('form') as HTMLFormElement).requestSubmit();
    fixture.detectChanges();

    expect(document.activeElement).toBe(compiled.querySelector('#email'));
  });

  it('clears field errors once the form becomes valid again', () => {
    const fixture = TestBed.createComponent(RegisterPage);
    const component = fixture.componentInstance;
    fixture.detectChanges();
    const compiled = fixture.nativeElement as HTMLElement;

    (compiled.querySelector('form') as HTMLFormElement).requestSubmit();
    fixture.detectChanges();
    expect(compiled.querySelector('#email-error')).toBeTruthy();

    component.form.setValue({
      email: 'newuser@example.test',
      password: VALID_PASSWORD,
      confirmPassword: VALID_PASSWORD,
    });
    fixture.detectChanges();

    expect(compiled.querySelector('#email-error')).toBeNull();
    expect(compiled.querySelector('#password-error')).toBeNull();
    expect(compiled.querySelector('#confirmPassword-error')).toBeNull();
  });

  it('shows the generic acknowledgement after a successful submit', () => {
    const fixture = TestBed.createComponent(RegisterPage);
    const component = fixture.componentInstance;

    component.form.setValue({
      email: 'newuser@example.test',
      password: VALID_PASSWORD,
      confirmPassword: VALID_PASSWORD,
    });
    component.submit();

    const req = httpMock.expectOne(`${API_BASE_URL}/auth/register`);
    req.flush({ status: 'ok', message: 'ack' });
    fixture.detectChanges();

    expect(component.submitted()).toBe(true);
    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.textContent).toContain('Tu cuenta ha sido creada. Ya puedes iniciar sesión.');
  });

  it('toggles password visibility with an accessible name that reflects state', () => {
    const fixture = TestBed.createComponent(RegisterPage);
    fixture.detectChanges();
    const compiled = fixture.nativeElement as HTMLElement;

    const input = compiled.querySelector('#password') as HTMLInputElement;
    const toggle = compiled.querySelector('.password-toggle') as HTMLButtonElement;

    expect(input.type).toBe('password');
    expect(toggle.getAttribute('aria-label')).toBe('Mostrar contraseña');

    toggle.click();
    fixture.detectChanges();

    expect(input.type).toBe('text');
    expect(toggle.getAttribute('aria-label')).toBe('Ocultar contraseña');
  });

  it('shows a validation error message on 422', () => {
    const fixture = TestBed.createComponent(RegisterPage);
    const component = fixture.componentInstance;

    component.form.setValue({
      email: 'newuser@example.test',
      password: VALID_PASSWORD,
      confirmPassword: VALID_PASSWORD,
    });
    component.submit();

    httpMock
      .expectOne(`${API_BASE_URL}/auth/register`)
      .flush(
        { detail: 'bad' },
        new HttpErrorResponse({ status: 422, statusText: 'Unprocessable Content' }),
      );

    expect(component.errorMessage()).toBe('Revisa el correo y la contraseña introducidos.');
    expect(component.submitted()).toBe(false);
  });

  describe('confirm-password field', () => {
    it('has autocomplete="new-password" and its toggle button has type="button"', () => {
      const fixture = TestBed.createComponent(RegisterPage);
      fixture.detectChanges();
      const compiled = fixture.nativeElement as HTMLElement;

      const confirmInput = compiled.querySelector('#confirmPassword') as HTMLInputElement;
      const toggles = compiled.querySelectorAll('.password-toggle');
      expect(confirmInput.getAttribute('autocomplete')).toBe('new-password');
      expect(confirmInput.type).toBe('password');
      expect(toggles.length).toBe(2);
      toggles.forEach((toggle) => expect(toggle.getAttribute('type')).toBe('button'));
    });

    it('shows "Confirma tu contraseña." when left empty and touched', () => {
      const fixture = TestBed.createComponent(RegisterPage);
      const component = fixture.componentInstance;
      fixture.detectChanges();
      const compiled = fixture.nativeElement as HTMLElement;

      component.form.controls.password.setValue(VALID_PASSWORD);
      component.form.controls.confirmPassword.markAsTouched();
      fixture.detectChanges();

      const confirmInput = compiled.querySelector('#confirmPassword') as HTMLInputElement;
      const confirmError = compiled.querySelector('#confirmPassword-error') as HTMLElement;
      expect(confirmInput.getAttribute('aria-invalid')).toBe('true');
      expect(confirmInput.getAttribute('aria-describedby')).toBe('confirmPassword-error');
      expect(confirmError.textContent).toContain('Confirma tu contraseña.');
    });

    it('shows "Las contraseñas no coinciden." when the values differ, and never leaks either value', () => {
      const fixture = TestBed.createComponent(RegisterPage);
      const component = fixture.componentInstance;
      fixture.detectChanges();
      const compiled = fixture.nativeElement as HTMLElement;

      component.form.controls.password.setValue(VALID_PASSWORD);
      component.form.controls.confirmPassword.setValue('a-different-password-456');
      component.form.controls.confirmPassword.markAsTouched();
      fixture.detectChanges();

      const confirmError = compiled.querySelector('#confirmPassword-error') as HTMLElement;
      expect(confirmError.textContent).toContain('Las contraseñas no coinciden.');
      expect(confirmError.textContent).not.toContain(VALID_PASSWORD);
      expect(confirmError.textContent).not.toContain('a-different-password-456');
      expect(compiled.innerHTML).not.toContain(VALID_PASSWORD);
      expect(compiled.innerHTML).not.toContain('a-different-password-456');
    });

    it('clears the mismatch error once both values match', () => {
      const fixture = TestBed.createComponent(RegisterPage);
      const component = fixture.componentInstance;
      fixture.detectChanges();
      const compiled = fixture.nativeElement as HTMLElement;

      component.form.controls.password.setValue(VALID_PASSWORD);
      component.form.controls.confirmPassword.setValue('a-different-password-456');
      component.form.controls.confirmPassword.markAsTouched();
      fixture.detectChanges();
      expect(compiled.querySelector('#confirmPassword-error')).toBeTruthy();

      component.form.controls.confirmPassword.setValue(VALID_PASSWORD);
      fixture.detectChanges();
      expect(compiled.querySelector('#confirmPassword-error')).toBeNull();
    });

    it('re-flags the mismatch if the original password changes after confirmation already matched', () => {
      const fixture = TestBed.createComponent(RegisterPage);
      const component = fixture.componentInstance;
      fixture.detectChanges();
      const compiled = fixture.nativeElement as HTMLElement;

      component.form.controls.password.setValue(VALID_PASSWORD);
      component.form.controls.confirmPassword.setValue(VALID_PASSWORD);
      component.form.controls.confirmPassword.markAsTouched();
      fixture.detectChanges();
      expect(compiled.querySelector('#confirmPassword-error')).toBeNull();

      component.form.controls.password.setValue('a-completely-different-password-789');
      fixture.detectChanges();

      expect(compiled.querySelector('#confirmPassword-error')?.textContent).toContain(
        'Las contraseñas no coinciden.',
      );
    });

    it('moves focus to confirmPassword on an invalid submit when it is the only invalid field', () => {
      const fixture = TestBed.createComponent(RegisterPage);
      const component = fixture.componentInstance;
      fixture.detectChanges();
      const compiled = fixture.nativeElement as HTMLElement;

      component.form.controls.email.setValue('newuser@example.test');
      component.form.controls.password.setValue(VALID_PASSWORD);
      component.form.controls.confirmPassword.setValue('mismatched-value-000');

      (compiled.querySelector('form') as HTMLFormElement).requestSubmit();
      fixture.detectChanges();

      expect(document.activeElement).toBe(compiled.querySelector('#confirmPassword'));
    });

    it('does not call the register service when the passwords do not match', () => {
      const fixture = TestBed.createComponent(RegisterPage);
      const component = fixture.componentInstance;
      fixture.detectChanges();

      component.form.controls.email.setValue('newuser@example.test');
      component.form.controls.password.setValue(VALID_PASSWORD);
      component.form.controls.confirmPassword.setValue('mismatched-value-000');
      component.submit();

      httpMock.expectNone(`${API_BASE_URL}/auth/register`);
    });

    it('never sends confirmPassword in the register request payload', () => {
      const fixture = TestBed.createComponent(RegisterPage);
      const component = fixture.componentInstance;
      fixture.detectChanges();

      component.form.setValue({
        email: 'newuser@example.test',
        password: VALID_PASSWORD,
        confirmPassword: VALID_PASSWORD,
      });
      component.submit();

      const req = httpMock.expectOne(`${API_BASE_URL}/auth/register`);
      expect(Object.keys(req.request.body)).toEqual(['email', 'password']);
      expect(JSON.stringify(req.request.body)).not.toContain('confirmPassword');
      req.flush({ status: 'ok' });
    });

    it('toggles confirm-password visibility independently, with its own accessible name', () => {
      const fixture = TestBed.createComponent(RegisterPage);
      fixture.detectChanges();
      const compiled = fixture.nativeElement as HTMLElement;

      const confirmInput = compiled.querySelector('#confirmPassword') as HTMLInputElement;
      const toggles = Array.from(
        compiled.querySelectorAll('.password-toggle'),
      ) as HTMLButtonElement[];
      const confirmToggle = toggles[1];
      const passwordInput = compiled.querySelector('#password') as HTMLInputElement;

      expect(confirmInput.type).toBe('password');
      expect(confirmToggle.getAttribute('aria-label')).toBe('Mostrar confirmación de contraseña');

      confirmToggle.click();
      fixture.detectChanges();

      expect(confirmInput.type).toBe('text');
      expect(passwordInput.type).toBe('password'); // unaffected by the other toggle
      expect(confirmToggle.getAttribute('aria-label')).toBe('Ocultar confirmación de contraseña');
    });
  });
});
