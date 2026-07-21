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

  it('renders exactly one emblem svg with four ornamental corners', () => {
    const fixture = TestBed.createComponent(HostComponent);
    fixture.detectChanges();
    const compiled = fixture.nativeElement as HTMLElement;

    expect(compiled.querySelectorAll('.emblem-svg').length).toBe(1);
    expect(compiled.querySelectorAll('.corner').length).toBe(4);
  });
});
