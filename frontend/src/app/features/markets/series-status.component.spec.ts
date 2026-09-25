import { Component, signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';

import { CandleSeriesOut } from '../../core/market-data/market-data.models';
import { isoAt, makeCandle, makeSeries } from '../../core/market-data/market-data.testing';
import { USER_TIME_ZONE } from '../../core/time/local-time';
import { SeriesStatusComponent } from './series-status.component';

@Component({
  imports: [SeriesStatusComponent],
  template: `<app-series-status [series]="series()" sourceName="Binance" />`,
})
class Host {
  readonly series = signal<CandleSeriesOut>(makeSeries());
}

// The candles in these tests are at 12:0x UTC. The zone is fixed here, never the machine's own.
function render(series: CandleSeriesOut, zone = 'Europe/Madrid'): HTMLElement {
  TestBed.configureTestingModule({ providers: [{ provide: USER_TIME_ZONE, useValue: zone }] });
  const fixture = TestBed.createComponent(Host);
  fixture.componentInstance.series.set(series);
  fixture.detectChanges();
  return fixture.nativeElement as HTMLElement;
}

const text = (element: HTMLElement) => (element.textContent ?? '').replace(/\s+/g, ' ').trim();

describe('SeriesStatusComponent', () => {
  it('shows a healthy series plainly: source, freshness, quality, no gaps and no banner', () => {
    const element = render(makeSeries());
    const content = text(element);

    expect(content).toContain('Binance');
    expect(content).toContain('Al día');
    expect(content).toContain('Calidad correcta');
    expect(content).toContain('Ninguno en el periodo mostrado');
    expect(content).toContain('GMT+2');
    expect(element.querySelector('.banner')).toBeNull();
    expect(element.querySelector('[role="alert"], [role="status"]')).toBeNull();
    expect(element.querySelector('.issues')).toBeNull();
  });

  it('says how long ago the last candle closed, as of the check', () => {
    // checked at 12:04:00, last candle closed at 12:03:00
    expect(text(render(makeSeries()))).toMatch(/La última vela cerró hace\s*1 min/);
  });

  it('gives no age when nothing is stored', () => {
    const empty = makeSeries({ candles: [] });
    expect(text(render(empty))).not.toContain('La última vela cerró hace');
  });

  it('describes the last attempt in words that fit an attempt', () => {
    const ok = makeSeries();
    ok.provider = { ...ok.provider!, last_status: 'DEGRADED' };
    expect(text(render(ok))).toContain('Último intento: con incidencias');
  });

  it('states when the last candle closed and when Freyja received it, with the zone', () => {
    const content = text(render(makeSeries()));

    // 12:02 UTC is 14:02 in Madrid in September (GMT+2): the person's own time, zone stated.
    expect(content).toMatch(/abre 24\/09\/2026, 14:02:00 GMT\+2/);
    expect(content).toMatch(/cierra 24\/09\/2026, 14:03:00 GMT\+2/);
    expect(content).toMatch(/Recibida por Freyja\s*24\/09\/2026, 14:03:00 GMT\+2/);
    expect(content).toMatch(/Comprobado\s*24\/09\/2026, 14:04:00 GMT\+2/);
    expect(content).not.toContain('UTC');
  });

  it('writes the same instants in whatever zone the person is in', () => {
    const bogota = text(render(makeSeries(), 'America/Bogota'));
    expect(bogota).toMatch(/abre 24\/09\/2026, 07:02:00 GMT-5/);
    expect(bogota).toMatch(/Comprobado\s*24\/09\/2026, 07:04:00 GMT-5/);

    TestBed.resetTestingModule(); // a test module can only be configured once
    const utc = text(render(makeSeries(), 'UTC'));
    expect(utc).toMatch(/abre 24\/09\/2026, 12:02:00 UTC/);
  });

  it('announces old data before anything else and never as current', () => {
    const series = makeSeries({
      quality: 'DEGRADED',
      issues: [{ code: 'STALE', detail: 'newest closed candle is 2026-09-24T10:00:00+00:00' }],
      freshness: {
        status: 'STALE',
        checked_at: isoAt(60),
        latest_open_time: isoAt(2),
        latest_close_time: isoAt(3),
        latest_received_at: isoAt(3),
      },
    });
    const element = render(series);

    const banner = element.querySelector('.banner');
    expect(banner?.getAttribute('role')).toBe('status');
    expect(banner?.textContent).toContain('⚠');
    expect(banner?.textContent).toContain('Calidad degradada');
    expect(banner?.textContent).toContain('No los uses como si fueran actuales');
    expect(text(element)).toContain('Desactualizado');
    expect(text(element)).toContain('Los datos están desactualizados');
    // The backend's technical text must not reach the screen.
    expect(text(element)).not.toContain('newest closed candle');
  });

  it('raises an alert when the data is not available at all', () => {
    const element = render(
      makeSeries({
        candles: [],
        quality: 'UNAVAILABLE',
        issues: [{ code: 'NO_DATA', detail: 'nothing stored' }],
        freshness: {
          status: 'NO_DATA',
          checked_at: isoAt(4),
          latest_open_time: null,
          latest_close_time: null,
          latest_received_at: null,
        },
        provider: null,
      }),
    );

    expect(element.querySelector('.banner')?.getAttribute('role')).toBe('alert');
    expect(text(element)).toContain('Datos no disponibles');
    expect(text(element)).toContain('Sin datos');
    expect(text(element)).toContain('Todavía no hay velas guardadas para esta serie.');
    expect(text(element)).toContain('Aún no se ha intentado sincronizar esta serie.');
  });

  it('lists each gap with its size and where it starts', () => {
    const element = render(
      makeSeries({
        quality: 'DEGRADED',
        issues: [{ code: 'GAP', detail: 'x' }],
        gaps: [
          { after_open_time: isoAt(1), missing: 1 },
          { after_open_time: isoAt(10), missing: 3 },
        ],
      }),
    );
    const items = [...element.querySelectorAll('.fact ul li')].map((li) => text(li as HTMLElement));

    expect(items).toHaveLength(2);
    expect(items[0]).toMatch(/^1 vela tras la de 24\/09\/2026, 14:01:00 GMT\+2/);
    expect(items[1]).toMatch(/^3 velas tras la de 24\/09\/2026, 14:10:00 GMT\+2/);
    expect(text(element)).not.toContain('Ninguno en el periodo mostrado');
  });

  it('shows a failing provider next to the data it could not refresh', () => {
    const element = render(
      makeSeries({
        quality: 'DEGRADED',
        issues: [{ code: 'PROVIDER_FAILING', detail: 'x' }],
        provider: {
          last_attempt_at: isoAt(4),
          last_success_at: null,
          last_status: 'UNAVAILABLE',
          last_issue_codes: ['PROVIDER_ERROR'],
          last_detail: 'provider error HTTP 503',
          consecutive_failures: 2,
        },
      }),
    );
    const content = text(element);

    expect(content).toContain('Último intento: falló');
    expect(content).toContain('Último éxito: nunca');
    expect(content).toContain('2 fallos seguidos');
    expect(content).toContain('puede haber velas más recientes que las mostradas');
    expect(content).not.toContain('provider error HTTP 503');
  });

  it('uses the singular for one failure', () => {
    const series = makeSeries();
    series.provider = { ...series.provider!, last_status: 'UNAVAILABLE', consecutive_failures: 1 };
    expect(text(render(series))).toContain('1 fallo seguido');
  });

  it('pairs each status with a symbol and text, not just a colour', () => {
    const element = render(makeSeries({ candles: [makeCandle(0)] }));
    const badges = [...element.querySelectorAll('.badge')];

    expect(badges.length).toBeGreaterThanOrEqual(3);
    for (const badge of badges) {
      expect(badge.querySelector('[aria-hidden="true"]')?.textContent?.trim()).toBeTruthy();
      expect((badge.textContent ?? '').trim().length).toBeGreaterThan(2);
    }
  });
});
