import { TestBed } from '@angular/core/testing';

import { RuneMark } from './rune-mark';

describe('RuneMark', () => {
  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [RuneMark],
    }).compileComponents();
  });

  it('renders exactly one accessible svg image with a non-empty aria-label', () => {
    const fixture = TestBed.createComponent(RuneMark);
    fixture.detectChanges();
    const compiled = fixture.nativeElement as HTMLElement;

    const svgs = compiled.querySelectorAll('svg[role="img"]');
    expect(svgs.length).toBe(1);
    expect(svgs[0].getAttribute('aria-label')).toContain('Freyja');
  });

  it('accepts a custom aria-label via input', () => {
    const fixture = TestBed.createComponent(RuneMark);
    fixture.componentRef.setInput('ariaLabel', 'Custom label');
    fixture.detectChanges();
    const compiled = fixture.nativeElement as HTMLElement;

    expect(compiled.querySelector('svg')?.getAttribute('aria-label')).toBe('Custom label');
  });

  it('uses a viewBox instead of fixed pixel dimensions, so it scales responsively', () => {
    const fixture = TestBed.createComponent(RuneMark);
    fixture.detectChanges();
    const compiled = fixture.nativeElement as HTMLElement;
    const svg = compiled.querySelector('svg') as SVGSVGElement;

    expect(svg.getAttribute('viewBox')).toBeTruthy();
    expect(svg.getAttribute('width')).toBeNull();
    expect(svg.getAttribute('height')).toBeNull();
  });

  it('draws the glyph as a single reusable vector path, not text relying on a runic font', () => {
    const fixture = TestBed.createComponent(RuneMark);
    fixture.detectChanges();
    const compiled = fixture.nativeElement as HTMLElement;

    const paths = compiled.querySelectorAll('path');
    expect(paths.length).toBe(1);
    expect(paths[0].getAttribute('d')?.length).toBeGreaterThan(0);
    expect(compiled.textContent?.trim()).toBe('');
  });
});
