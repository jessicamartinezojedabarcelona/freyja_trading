import { Location } from '@angular/common';
import { HttpErrorResponse, provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { ActivatedRoute, provideRouter } from '@angular/router';

import { API_BASE_URL } from '../../core/config/api.config';
import { ResetPasswordPage } from './reset-password.page';

const VALID_PASSWORD = 'a-brand-new-strong-password';

function activatedRouteWithToken(token: string | null): Partial<ActivatedRoute> {
  return {
    snapshot: {
      fragment: token ? `token=${token}` : null,
    } as ActivatedRoute['snapshot'],
  };
}

describe('ResetPasswordPage', () => {
  let httpMock: HttpTestingController;

  async function setup(
    token: string | null,
  ): Promise<ReturnType<typeof TestBed.createComponent<ResetPasswordPage>>> {
    await TestBed.configureTestingModule({
      imports: [ResetPasswordPage],
      providers: [
        provideRouter([]),
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: ActivatedRoute, useValue: activatedRouteWithToken(token) },
      ],
    }).compileComponents();

    httpMock = TestBed.inject(HttpTestingController);
    const fixture = TestBed.createComponent(ResetPasswordPage);
    fixture.detectChanges();
    return fixture;
  }

  afterEach(() => {
    httpMock.verify();
  });

  it('shows invalid state immediately when there is no token in the URL fragment', async () => {
    const fixture = await setup(null);
    expect(fixture.componentInstance.state()).toBe('invalid');
  });

  it('strips the token from the visible URL as soon as it is read', async () => {
    const replaceStateSpy = vi.spyOn(Location.prototype, 'replaceState');
    await setup('a-valid-token');
    expect(replaceStateSpy).toHaveBeenCalled();
  });

  it('toggles password visibility with an accessible name that reflects state', async () => {
    const fixture = await setup('a-valid-token');
    const compiled = fixture.nativeElement as HTMLElement;

    const input = compiled.querySelector('#newPassword') as HTMLInputElement;
    const toggle = compiled.querySelector('.password-toggle') as HTMLButtonElement;

    expect(input.type).toBe('password');
    expect(toggle.getAttribute('aria-label')).toBe('Mostrar contraseña');

    toggle.click();
    fixture.detectChanges();

    expect(input.type).toBe('text');
    expect(toggle.getAttribute('aria-label')).toBe('Ocultar contraseña');
  });

  it('does not disable the submit button merely for being invalid', async () => {
    const fixture = await setup('a-valid-token');
    const button = fixture.nativeElement.querySelector(
      'button[type="submit"]',
    ) as HTMLButtonElement;
    expect(button.disabled).toBe(false);
  });

  it('references the persistent hint by default and adds the error id once invalid and touched', async () => {
    const fixture = await setup('a-valid-token');
    const component = fixture.componentInstance;
    const compiled = fixture.nativeElement as HTMLElement;

    const input = compiled.querySelector('#newPassword') as HTMLInputElement;
    expect(input.getAttribute('aria-describedby')).toBe('newPassword-hint');

    component.form.controls.newPassword.setValue('short');
    component.form.controls.newPassword.markAsTouched();
    fixture.detectChanges();

    expect(input.getAttribute('aria-describedby')).toBe('newPassword-hint newPassword-error');
    expect(compiled.querySelector('#newPassword-error')?.textContent).toContain(
      'al menos 12 caracteres',
    );
    expect(compiled.querySelector('#newPassword-error')?.textContent).not.toContain('short');
  });

  it('moves focus to the password field on an invalid submit attempt', async () => {
    const fixture = await setup('a-valid-token');
    const compiled = fixture.nativeElement as HTMLElement;

    (compiled.querySelector('form') as HTMLFormElement).requestSubmit();
    fixture.detectChanges();

    expect(document.activeElement).toBe(compiled.querySelector('#newPassword'));
  });

  it('submits the new password and shows success', async () => {
    const fixture = await setup('a-valid-token');
    const component = fixture.componentInstance;

    component.form.setValue({ newPassword: VALID_PASSWORD, confirmPassword: VALID_PASSWORD });
    component.submit();

    const req = httpMock.expectOne(`${API_BASE_URL}/auth/reset-password`);
    expect(req.request.body).toEqual({
      token: 'a-valid-token',
      new_password: VALID_PASSWORD,
    });
    req.flush({ status: 'ok' });

    expect(component.state()).toBe('success');
  });

  it('shows expired state on TOKEN_EXPIRED', async () => {
    const fixture = await setup('an-expired-token');
    const component = fixture.componentInstance;

    component.form.setValue({ newPassword: VALID_PASSWORD, confirmPassword: VALID_PASSWORD });
    component.submit();

    httpMock
      .expectOne(`${API_BASE_URL}/auth/reset-password`)
      .flush(
        { detail: 'TOKEN_EXPIRED' },
        new HttpErrorResponse({ status: 400, statusText: 'Bad Request' }),
      );

    expect(component.state()).toBe('expired');
  });

  it('shows invalid state on TOKEN_INVALID', async () => {
    const fixture = await setup('a-bogus-token');
    const component = fixture.componentInstance;

    component.form.setValue({ newPassword: VALID_PASSWORD, confirmPassword: VALID_PASSWORD });
    component.submit();

    httpMock
      .expectOne(`${API_BASE_URL}/auth/reset-password`)
      .flush(
        { detail: 'TOKEN_INVALID' },
        new HttpErrorResponse({ status: 400, statusText: 'Bad Request' }),
      );

    expect(component.state()).toBe('invalid');
  });

  describe('confirm-password field', () => {
    it('has autocomplete="new-password" and its toggle button has type="button"', async () => {
      const fixture = await setup('a-valid-token');
      const compiled = fixture.nativeElement as HTMLElement;

      const confirmInput = compiled.querySelector('#confirmPassword') as HTMLInputElement;
      const toggles = compiled.querySelectorAll('.password-toggle');
      expect(confirmInput.getAttribute('autocomplete')).toBe('new-password');
      expect(confirmInput.type).toBe('password');
      expect(toggles.length).toBe(2);
      toggles.forEach((toggle) => expect(toggle.getAttribute('type')).toBe('button'));
    });

    it('shows "Confirma la nueva contraseña." when left empty and touched', async () => {
      const fixture = await setup('a-valid-token');
      const component = fixture.componentInstance;
      const compiled = fixture.nativeElement as HTMLElement;

      component.form.controls.newPassword.setValue(VALID_PASSWORD);
      component.form.controls.confirmPassword.markAsTouched();
      fixture.detectChanges();

      const confirmInput = compiled.querySelector('#confirmPassword') as HTMLInputElement;
      const confirmError = compiled.querySelector('#confirmPassword-error') as HTMLElement;
      expect(confirmInput.getAttribute('aria-invalid')).toBe('true');
      expect(confirmInput.getAttribute('aria-describedby')).toBe('confirmPassword-error');
      expect(confirmError.textContent).toContain('Confirma la nueva contraseña.');
    });

    it('shows "Las contraseñas no coinciden." when the values differ, and never leaks either value', async () => {
      const fixture = await setup('a-valid-token');
      const component = fixture.componentInstance;
      const compiled = fixture.nativeElement as HTMLElement;

      component.form.controls.newPassword.setValue(VALID_PASSWORD);
      component.form.controls.confirmPassword.setValue('a-different-password-456');
      component.form.controls.confirmPassword.markAsTouched();
      fixture.detectChanges();

      const confirmError = compiled.querySelector('#confirmPassword-error') as HTMLElement;
      expect(confirmError.textContent).toContain('Las contraseñas no coinciden.');
      expect(compiled.innerHTML).not.toContain(VALID_PASSWORD);
      expect(compiled.innerHTML).not.toContain('a-different-password-456');
    });

    it('clears the mismatch error once both values match', async () => {
      const fixture = await setup('a-valid-token');
      const component = fixture.componentInstance;
      const compiled = fixture.nativeElement as HTMLElement;

      component.form.controls.newPassword.setValue(VALID_PASSWORD);
      component.form.controls.confirmPassword.setValue('a-different-password-456');
      component.form.controls.confirmPassword.markAsTouched();
      fixture.detectChanges();
      expect(compiled.querySelector('#confirmPassword-error')).toBeTruthy();

      component.form.controls.confirmPassword.setValue(VALID_PASSWORD);
      fixture.detectChanges();
      expect(compiled.querySelector('#confirmPassword-error')).toBeNull();
    });

    it('re-flags the mismatch if the original password changes after confirmation already matched', async () => {
      const fixture = await setup('a-valid-token');
      const component = fixture.componentInstance;
      const compiled = fixture.nativeElement as HTMLElement;

      component.form.controls.newPassword.setValue(VALID_PASSWORD);
      component.form.controls.confirmPassword.setValue(VALID_PASSWORD);
      component.form.controls.confirmPassword.markAsTouched();
      fixture.detectChanges();
      expect(compiled.querySelector('#confirmPassword-error')).toBeNull();

      component.form.controls.newPassword.setValue('a-completely-different-password-789');
      fixture.detectChanges();

      expect(compiled.querySelector('#confirmPassword-error')?.textContent).toContain(
        'Las contraseñas no coinciden.',
      );
    });

    it('moves focus to confirmPassword on an invalid submit when it is the only invalid field', async () => {
      const fixture = await setup('a-valid-token');
      const component = fixture.componentInstance;
      const compiled = fixture.nativeElement as HTMLElement;

      component.form.controls.newPassword.setValue(VALID_PASSWORD);
      component.form.controls.confirmPassword.setValue('mismatched-value-000');

      (compiled.querySelector('form') as HTMLFormElement).requestSubmit();
      fixture.detectChanges();

      expect(document.activeElement).toBe(compiled.querySelector('#confirmPassword'));
    });

    it('does not call the reset-password service when the passwords do not match', async () => {
      const fixture = await setup('a-valid-token');
      const component = fixture.componentInstance;

      component.form.controls.newPassword.setValue(VALID_PASSWORD);
      component.form.controls.confirmPassword.setValue('mismatched-value-000');
      component.submit();

      httpMock.expectNone(`${API_BASE_URL}/auth/reset-password`);
    });

    it('never sends confirmPassword in the reset-password request payload', async () => {
      const fixture = await setup('a-valid-token');
      const component = fixture.componentInstance;

      component.form.setValue({ newPassword: VALID_PASSWORD, confirmPassword: VALID_PASSWORD });
      component.submit();

      const req = httpMock.expectOne(`${API_BASE_URL}/auth/reset-password`);
      expect(Object.keys(req.request.body)).toEqual(['token', 'new_password']);
      expect(JSON.stringify(req.request.body)).not.toContain('confirmPassword');
      req.flush({ status: 'ok' });
    });

    it('toggles confirm-password visibility independently, with its own accessible name', async () => {
      const fixture = await setup('a-valid-token');
      const compiled = fixture.nativeElement as HTMLElement;

      const confirmInput = compiled.querySelector('#confirmPassword') as HTMLInputElement;
      const toggles = Array.from(
        compiled.querySelectorAll('.password-toggle'),
      ) as HTMLButtonElement[];
      const confirmToggle = toggles[1];
      const passwordInput = compiled.querySelector('#newPassword') as HTMLInputElement;

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
