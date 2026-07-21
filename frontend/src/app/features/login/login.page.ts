import { HttpErrorResponse } from '@angular/common/http';
import { Component, ElementRef, ViewChild, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';

import { AuthService } from '../../core/auth/auth.service';
import { AuthShell } from '../../shared/auth-shell/auth-shell';
import { shouldShowFieldError } from '../../shared/form-errors';
import { humanizeUnexpectedError } from '../../shared/http-error-message';

@Component({
  selector: 'app-login-page',
  imports: [ReactiveFormsModule, RouterLink, AuthShell],
  templateUrl: './login.page.html',
})
export class LoginPage {
  private readonly formBuilder = inject(FormBuilder);
  private readonly authService = inject(AuthService);
  private readonly router = inject(Router);
  private readonly route = inject(ActivatedRoute);

  @ViewChild('identifierInput') private readonly identifierInput?: ElementRef<HTMLInputElement>;
  @ViewChild('passwordInput') private readonly passwordInput?: ElementRef<HTMLInputElement>;

  readonly submitting = signal(false);
  readonly errorMessage = signal<string | null>(null);
  readonly sessionExpired = signal(this.route.snapshot.queryParamMap.get('expired') === '1');
  readonly passwordVisible = signal(false);
  readonly attemptedSubmit = signal(false);

  readonly form = this.formBuilder.nonNullable.group({
    identifier: ['', [Validators.required]],
    password: ['', [Validators.required]],
  });

  togglePasswordVisibility(): void {
    this.passwordVisible.update((visible) => !visible);
  }

  identifierError(): string | null {
    const control = this.form.controls.identifier;
    if (!shouldShowFieldError(control, this.attemptedSubmit())) {
      return null;
    }
    return 'Introduce tu correo.';
  }

  passwordError(): string | null {
    const control = this.form.controls.password;
    if (!shouldShowFieldError(control, this.attemptedSubmit())) {
      return null;
    }
    return 'Introduce tu contraseña.';
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
    this.sessionExpired.set(false);

    const { identifier, password } = this.form.getRawValue();
    this.authService.login(identifier, password).subscribe({
      next: () => {
        this.submitting.set(false);
        void this.router.navigateByUrl('/');
      },
      error: (error: HttpErrorResponse) => {
        this.submitting.set(false);
        this.errorMessage.set(this.messageFor(error));
      },
    });
  }

  private messageFor(error: HttpErrorResponse): string {
    if (error.status === 429) {
      return 'Demasiados intentos. Vuelve a intentarlo más tarde.';
    }
    if (error.status === 401) {
      return 'Correo o contraseña incorrectos.';
    }
    return humanizeUnexpectedError(error, 'No se pudo iniciar sesión. Inténtalo de nuevo.');
  }

  private focusFirstInvalidField(): void {
    if (this.form.controls.identifier.invalid) {
      this.identifierInput?.nativeElement.focus();
      return;
    }
    if (this.form.controls.password.invalid) {
      this.passwordInput?.nativeElement.focus();
    }
  }
}
