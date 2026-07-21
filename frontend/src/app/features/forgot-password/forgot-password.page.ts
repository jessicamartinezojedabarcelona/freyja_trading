import { Component, ElementRef, ViewChild, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { RouterLink } from '@angular/router';

import { AuthService } from '../../core/auth/auth.service';
import { AuthShell } from '../../shared/auth-shell/auth-shell';
import { shouldShowFieldError } from '../../shared/form-errors';

@Component({
  selector: 'app-forgot-password-page',
  imports: [ReactiveFormsModule, RouterLink, AuthShell],
  templateUrl: './forgot-password.page.html',
})
export class ForgotPasswordPage {
  private readonly formBuilder = inject(FormBuilder);
  private readonly authService = inject(AuthService);

  @ViewChild('emailInput') private readonly emailInput?: ElementRef<HTMLInputElement>;

  readonly submitting = signal(false);
  readonly submitted = signal(false);
  readonly attemptedSubmit = signal(false);

  readonly form = this.formBuilder.nonNullable.group({
    email: ['', [Validators.required, Validators.email]],
  });

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

  submit(): void {
    this.attemptedSubmit.set(true);
    if (this.form.invalid || this.submitting()) {
      if (this.form.invalid) {
        this.emailInput?.nativeElement.focus();
      }
      return;
    }
    this.submitting.set(true);

    const { email } = this.form.getRawValue();
    this.authService.forgotPassword(email).subscribe({
      // Same generic acknowledgement on success or failure: never reveal
      // whether the account exists.
      next: () => this.finish(),
      error: () => this.finish(),
    });
  }

  private finish(): void {
    this.submitting.set(false);
    this.submitted.set(true);
  }
}
