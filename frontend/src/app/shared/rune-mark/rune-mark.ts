import { Component, input } from '@angular/core';

@Component({
  selector: 'app-rune-mark',
  imports: [],
  templateUrl: './rune-mark.html',
  styleUrl: './rune-mark.scss',
})
export class RuneMark {
  readonly ariaLabel = input<string>('Rune fé (ᚠ), inicial de Freyja en futhark reciente');
}
