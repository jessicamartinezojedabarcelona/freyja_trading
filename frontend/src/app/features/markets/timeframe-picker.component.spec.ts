import { Component, signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';

import { CATALOG_TIMEFRAMES } from '../../core/market-data/market-data.testing';
import { buildPeriodOptions } from './periods';
import { TimeframePickerComponent } from './timeframe-picker.component';

@Component({
  imports: [TimeframePickerComponent],
  template: `<app-timeframe-picker
    [options]="options"
    [selected]="selected()"
    (chosen)="picked.push($event)"
  />`,
})
class Host {
  readonly options = buildPeriodOptions(CATALOG_TIMEFRAMES);
  readonly selected = signal<string | null>('1m');
  readonly picked: string[] = [];
}

function setup() {
  const fixture = TestBed.createComponent(Host);
  fixture.detectChanges();
  const element = fixture.nativeElement as HTMLElement;
  const buttons = () => [...element.querySelectorAll<HTMLButtonElement>('button.period')];
  const byLabel = (label: string) =>
    buttons().find((b) => (b.textContent ?? '').replace(/\s+/g, ' ').trim().startsWith(label));
  return { fixture, element, buttons, byLabel };
}

describe('TimeframePickerComponent', () => {
  it('shows all sixteen periods in four labelled groups', () => {
    const { element, buttons } = setup();

    expect(buttons()).toHaveLength(16);
    const groups = [...element.querySelectorAll('[role="group"][aria-label]')]
      .map((g) => g.getAttribute('aria-label'))
      .filter((label) => label !== 'Periodo de las velas');
    expect(groups).toEqual(['Segundos', 'Minutos', 'Horas', 'Días y más']);
  });

  it('marks the selected period for assistive technology, and only that one', () => {
    const { buttons } = setup();
    const pressed = buttons().filter((b) => b.getAttribute('aria-pressed') === 'true');

    expect(pressed).toHaveLength(1);
    expect(pressed[0].textContent).toContain('1m');
  });

  it('emits the chosen period when an enabled one is clicked', () => {
    const { fixture, byLabel } = setup();

    byLabel('15m')!.click();

    expect(fixture.componentInstance.picked).toEqual(['15m']);
  });

  it('keeps periods the catalog does not enable visible, disabled and explained', () => {
    const { fixture, byLabel } = setup();
    const thirtySeconds = byLabel('🔒 30seg')!;

    expect(thirtySeconds.disabled).toBe(true);
    expect(thirtySeconds.getAttribute('title')).toBe('Aún no disponible para este instrumento');
    expect(thirtySeconds.textContent).toContain('aún no disponible');
    thirtySeconds.click();
    expect(fixture.componentInstance.picked).toEqual([]);
  });

  it('follows the selection', () => {
    const { fixture, buttons } = setup();

    fixture.componentInstance.selected.set('4h');
    fixture.detectChanges();

    const pressed = buttons().filter((b) => b.getAttribute('aria-pressed') === 'true');
    expect(pressed.map((b) => (b.textContent ?? '').trim())).toEqual(['4hs']);
  });
});
