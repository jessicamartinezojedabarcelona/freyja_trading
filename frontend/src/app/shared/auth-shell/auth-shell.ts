import { Component, input } from '@angular/core';

import { RuneMark } from '../rune-mark/rune-mark';

@Component({
  selector: 'app-auth-shell',
  imports: [RuneMark],
  templateUrl: './auth-shell.html',
  styleUrl: './auth-shell.scss',
})
export class AuthShell {
  readonly heading = input<string>('');
  readonly subtitle = input<string>('');
}
