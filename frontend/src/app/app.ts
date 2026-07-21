import { Component, inject } from '@angular/core';
import { RouterOutlet } from '@angular/router';

import { AuthService } from './core/auth/auth.service';

@Component({
  selector: 'app-root',
  imports: [RouterOutlet],
  templateUrl: './app.html',
  styleUrl: './app.scss',
})
export class App {
  private readonly authService = inject(AuthService);

  constructor() {
    // Fire-and-forget: primes the CSRF cookie on first load, regardless of
    // which route the user lands on — a page like /reset-password never
    // goes through the auth guard. Uses the dedicated GET /auth/csrf
    // endpoint, not /auth/me: priming CSRF should not be a side effect of a
    // session/identity check.
    this.authService.primeCsrf().subscribe({ error: () => undefined });
  }
}
