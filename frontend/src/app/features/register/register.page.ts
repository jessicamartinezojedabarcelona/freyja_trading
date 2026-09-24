import { HttpErrorResponse } from '@angular/common/http';
import { Component, ElementRef, ViewChild, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { RouterLink } from '@angular/router';

import { AuthService } from '../../core/auth/auth.service';
import { AuthShell } from '../../shared/auth-shell/auth-shell';
import { passwordsMatchValidator, shouldShowFieldError } from '../../shared/form-errors';
import { humanizeUnexpectedError } from '../../shared/http-error-message';

@Component({
  selector: 'app-register-page',
  imports: [ReactiveFormsModule, RouterLink, AuthShell],
  templateUrl: './register.page.html',
})
export class RegisterPage {
  private readonly formBuilder = inject(FormBuilder);
  private readonly authService = inject(AuthService);

  @ViewChild('emailInput') private readonly emailInput?: ElementRef<HTMLInputElement>;
  @ViewChild('passwordInput') private readonly passwordInput?: ElementRef<HTMLInputElement>;
  @ViewChild('confirmPasswordInput')
  private readonly confirmPasswordInput?: ElementRef<HTMLInputElement>;

  readonly submitting = signal(false);
  readonly submitted = signal(false);
  readonly errorMessage = signal<string | null>(null);
  readonly passwordVisible = signal(false);
  readonly confirmPasswordVisible = signal(false);
  readonly attemptedSubmit = signal(false);

  readonly form = this.formBuilder.nonNullable.group({
    email: ['', [Validators.required, Validators.email]],
    password: ['', [Validators.required, Validators.minLength(12)]],
    confirmPassword: ['', [Validators.required, passwordsMatchValidator('password')]],
  });

  constructor() {
    // The confirm-password validator reads a sibling control's value, which
    // Angular does not automatically re-check — without this, editing the
    // original password after already confirming it would leave a stale
    // "match" result instead of re-flagging the mismatch.
    this.form.controls.password.valueChanges.pipe(takeUntilDestroyed()).subscribe(() => {
      this.form.controls.confirmPassword.updateValueAndValidity();
    });
  }

  togglePasswordVisibility(): void {
    this.passwordVisible.update((visible) => !visible);
  }

  toggleConfirmPasswordVisibility(): void {
    this.confirmPasswordVisible.update((visible) => !visible);
  }

  emailError(): string | null {
    const control = this.form.controls.email;
    if (!shouldShowFieldError(control, this.attemptedSubmit())) {
      return null;
    }
    if (control.hasError('required')) {
      return 'Introduce tu correo.';
    }
    return 'El formato del correo no es válido.';
  }

  passwordError(): string | null {
    const control = this.form.controls.password;
    if (!shouldShowFieldError(control, this.attemptedSubmit())) {
      return null;
    }
    if (control.hasError('required')) {
      return 'Introduce tu contraseña.';
    }
    return 'La contraseña debe tener al menos 12 caracteres.';
  }

  confirmPasswordError(): string | null {
    const control = this.form.controls.confirmPassword;
    if (!shouldShowFieldError(control, this.attemptedSubmit())) {
      return null;
    }
    if (control.hasError('required')) {
      return 'Confirma tu contraseña.';
    }
    if (control.hasError('mismatch')) {
      return 'Las contraseñas no coinciden.';
    }
    return null;
  }

  submit(): void {
    this.attemptedSubmit.set(true);
    if (this.form.invalid || this.submitting()) {
      if (this.form.invalid) {
        this.focusFirstInvalidField();
      }
      return;
    }

    this.submitting.set(true);
    this.errorMessage.set(null);

    const { email, password } = this.form.getRawValue();
    this.authService.register(email, password).subscribe({
      next: () => {
        this.submitting.set(false);
        this.submitted.set(true);
      },
      error: (error: HttpErrorResponse) => {
        this.submitting.set(false);
        this.errorMessage.set(this.messageFor(error));
      },
    });
  }

  private messageFor(error: HttpErrorResponse): string {
    if (error.status === 422) {
      return 'Revisa el correo y la contraseña introducidos.';
    }
    return humanizeUnexpectedError(error, 'No se pudo completar el registro. Inténtalo de nuevo.');
  }

  private focusFirstInvalidField(): void {
    if (this.form.controls.email.invalid) {
      this.emailInput?.nativeElement.focus();
      return;
    }
    if (this.form.controls.password.invalid) {
      this.passwordInput?.nativeElement.focus();
      return;
    }
    if (this.form.controls.confirmPassword.invalid) {
      this.confirmPasswordInput?.nativeElement.focus();
    }
  }
}
