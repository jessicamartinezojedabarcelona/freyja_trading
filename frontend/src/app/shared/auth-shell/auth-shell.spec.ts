import { Component } from '@angular/core';
import { TestBed } from '@angular/core/testing';

import { AuthShell } from './auth-shell';

@Component({
  selector: 'app-host',
  imports: [AuthShell],
  template: `
    <app-auth-shell heading="Test heading" subtitle="Test subtitle">
      <p class="probe">card body</p>
      <p below-card class="probe-below">below card</p>
    </app-auth-shell>
  `,
})
class HostComponent {}

describe('AuthShell', () => {
  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [HostComponent],
    }).compileComponents();
  });

  it('renders the Freyja wordmark and the given heading/subtitle', () => {
    const fixture = TestBed.createComponent(HostComponent);
    fixture.detectChanges();
    const compiled = fixture.nativeElement as HTMLElement;

    expect(compiled.textContent).toContain('Freyja');
    expect(compiled.textContent).toContain('Test heading');
    expect(compiled.textContent).toContain('Test subtitle');
  });

  it('projects the card body and the below-card content', () => {
    const fixture = TestBed.createComponent(HostComponent);
    fixture.detectChanges();
    const compiled = fixture.nativeElement as HTMLElement;

    expect(compiled.querySelector('.probe')?.textContent).toContain('card body');
    expect(compiled.querySelector('.probe-below')?.textContent).toContain('below card');
  });

  it('renders exactly one emblem ring svg with four ornamental corners', () => {
    const fixture = TestBed.createComponent(HostComponent);
    fixture.detectChanges();
    const compiled = fixture.nativeElement as HTMLElement;

    expect(compiled.querySelectorAll('.emblem-ring-svg').length).toBe(1);
    expect(compiled.querySelectorAll('.corner').length).toBe(4);
  });

  it('uses the single rune-mark resource in the header emblem, and nowhere else', () => {
    const fixture = TestBed.createComponent(HostComponent);
    fixture.detectChanges();
    const compiled = fixture.nativeElement as HTMLElement;

    const marks = compiled.querySelectorAll('app-rune-mark');
    expect(marks.length).toBe(1);
    expect(compiled.querySelector('.emblem app-rune-mark')).toBeTruthy();
    expect(compiled.querySelector('.quote app-rune-mark')).toBeNull();
  });

  it('hides the decorative rune mark from assistive tech, since the visible text already says "Freyja"', () => {
    const fixture = TestBed.createComponent(HostComponent);
    fixture.detectChanges();
    const compiled = fixture.nativeElement as HTMLElement;

    compiled.querySelectorAll('app-rune-mark').forEach((mark) => {
      expect(mark.getAttribute('aria-hidden')).toBe('true');
    });
  });

  it('does not render any of the old inconsistent symbols it replaced', () => {
    const fixture = TestBed.createComponent(HostComponent);
    fixture.detectChanges();
    const compiled = fixture.nativeElement as HTMLElement;

    expect(compiled.textContent).not.toContain('Ψ');
    expect(compiled.querySelector('.emblem-glyph')).toBeNull();
    expect(compiled.querySelector('.quote-glyph')).toBeNull();
  });

  it('sizes the emblem mark responsively via width, not fixed pixel dimensions', () => {
    const fixture = TestBed.createComponent(HostComponent);
    fixture.detectChanges();
    const compiled = fixture.nativeElement as HTMLElement;

    compiled.querySelectorAll('app-rune-mark svg').forEach((svg) => {
      expect(svg.getAttribute('viewBox')).toBeTruthy();
      expect(svg.getAttribute('width')).toBeNull();
    });
  });
});
