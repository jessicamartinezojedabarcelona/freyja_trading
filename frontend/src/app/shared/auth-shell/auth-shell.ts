import { Component, input } from '@angular/core';

@Component({
  selector: 'app-auth-shell',
  imports: [],
  templateUrl: './auth-shell.html',
  styleUrl: './auth-shell.scss',
})
export class AuthShell {
  readonly heading = input<string>('');
  readonly subtitle = input<string>('');
}
