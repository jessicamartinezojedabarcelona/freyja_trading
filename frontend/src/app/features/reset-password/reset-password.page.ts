import { Location } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { Component, ElementRef, ViewChild, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { ActivatedRoute, RouterLink } from '@angular/router';

import { AuthService } from '../../core/auth/auth.service';
import { AuthShell } from '../../shared/auth-shell/auth-shell';
import { extractTokenFromFragment } from '../../shared/fragment-token';
import { passwordsMatchValidator, shouldShowFieldError } from '../../shared/form-errors';
import { humanizeUnexpectedError } from '../../shared/http-error-message';

type ResetState = 'form' | 'success' | 'invalid' | 'expired';

@Component({
  selector: 'app-reset-password-page',
  imports: [ReactiveFormsModule, RouterLink, AuthShell],
  templateUrl: './reset-password.page.html',
})
export class ResetPasswordPage {
  private readonly formBuilder = inject(FormBuilder);
  private readonly authService = inject(AuthService);
  private readonly route = inject(ActivatedRoute);
  private readonly location = inject(Location);

  private readonly token = extractTokenFromFragment(this.route.snapshot.fragment);

  @ViewChild('newPasswordInput') private readonly newPasswordInput?: ElementRef<HTMLInputElement>;
  @ViewChild('confirmPasswordInput')
  private readonly confirmPasswordInput?: ElementRef<HTMLInputElement>;

  readonly state = signal<ResetState>(this.token ? 'form' : 'invalid');
  readonly submitting = signal(false);
  readonly errorMessage = signal<string | null>(null);
  readonly passwordVisible = signal(false);
  readonly confirmPasswordVisible = signal(false);
  readonly attemptedSubmit = signal(false);

  readonly form = this.formBuilder.nonNullable.group({
    newPassword: ['', [Validators.required, Validators.minLength(12)]],
    confirmPassword: ['', [Validators.required, passwordsMatchValidator('newPassword')]],
  });

  constructor() {
    // Strip the token from the visible URL/history immediately on load — it
    // is submitted once, in the POST body below, never re-read from the URL.
    this.location.replaceState(this.location.path(false));

    // See the equivalent comment in register.page.ts: the confirm-password
    // validator reads a sibling control, so it must be re-run explicitly
    // whenever that sibling changes.
    this.form.controls.newPassword.valueChanges.pipe(takeUntilDestroyed()).subscribe(() => {
      this.form.controls.confirmPassword.updateValueAndValidity();
    });
  }

  togglePasswordVisibility(): void {
    this.passwordVisible.update((visible) => !visible);
  }

  toggleConfirmPasswordVisibility(): void {
    this.confirmPasswordVisible.update((visible) => !visible);
  }

  newPasswordError(): string | null {
    const control = this.form.controls.newPassword;
    if (!shouldShowFieldError(control, this.attemptedSubmit())) {
      return null;
    }
    if (control.hasError('required')) {
      return 'Introduce la nueva contraseña.';
    }
    return 'La contraseña debe tener al menos 12 caracteres.';
  }

  confirmPasswordError(): string | null {
    const control = this.form.controls.confirmPassword;
    if (!shouldShowFieldError(control, this.attemptedSubmit())) {
      return null;
    }
    if (control.hasError('required')) {
      return 'Confirma la nueva contraseña.';
    }
    if (control.hasError('mismatch')) {
      return 'Las contraseñas no coinciden.';
    }
    return null;
  }

  submit(): void {
    this.attemptedSubmit.set(true);
    if (this.form.invalid || this.submitting() || !this.token) {
      if (this.form.invalid) {
        this.focusFirstInvalidField();
      }
      return;
    }
    this.submitting.set(true);
    this.errorMessage.set(null);

    const { newPassword } = this.form.getRawValue();
    this.authService.resetPassword(this.token, newPassword).subscribe({
      next: () => {
        this.submitting.set(false);
        this.state.set('success');
      },
      error: (error: HttpErrorResponse) => {
        this.submitting.set(false);
        const detail: unknown = error.error?.detail;
        if (detail === 'TOKEN_EXPIRED') {
          this.state.set('expired');
          return;
        }
        if (detail === 'TOKEN_INVALID') {
          this.state.set('invalid');
          return;
        }
        this.errorMessage.set(
          humanizeUnexpectedError(
            error,
            'No se pudo restablecer la contraseña. Inténtalo de nuevo.',
          ),
        );
      },
    });
  }

  private focusFirstInvalidField(): void {
    if (this.form.controls.newPassword.invalid) {
      this.newPasswordInput?.nativeElement.focus();
      return;
    }
    if (this.form.controls.confirmPassword.invalid) {
      this.confirmPasswordInput?.nativeElement.focus();
    }
  }
}
