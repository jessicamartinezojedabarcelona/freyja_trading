import { Component, signal } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';

import { CandleChartComponent } from './candle-chart.component';
import { ChartData } from './chart-data';
import { CHART_FACTORY, ChartHandle } from './chart-handle';

const data = (closes: number[]): ChartData => ({
  candles: closes.map((close, index) => ({
    time: 1_000 + index * 60,
    open: close,
    high: close,
    low: close,
    close,
    volume: 1,
  })),
  precision: 2,
});

class FakeChart implements ChartHandle {
  readonly drawn: { data: ChartData; resetView: boolean }[] = [];
  destroyed = 0;

  setData(payload: ChartData, options: { resetView: boolean }): void {
    this.drawn.push({ data: payload, resetView: options.resetView });
  }

  destroy(): void {
    this.destroyed += 1;
  }
}

@Component({
  imports: [CandleChartComponent],
  template: `<app-candle-chart [data]="data()" [label]="label()" [seriesKey]="key()" />`,
})
class Host {
  readonly data = signal(data([1, 2, 3]));
  readonly label = signal('Gráfico de velas de prueba');
  readonly key = signal('A');
}

describe('CandleChartComponent', () => {
  let chart: FakeChart;
  let created: HTMLElement[];

  async function setup(
    factory?: (host: HTMLElement) => Promise<ChartHandle>,
  ): Promise<ComponentFixture<Host>> {
    chart = new FakeChart();
    created = [];
    TestBed.configureTestingModule({
      providers: [
        {
          provide: CHART_FACTORY,
          useValue:
            factory ??
            ((host: HTMLElement) => {
              created.push(host);
              return Promise.resolve(chart);
            }),
        },
      ],
    });
    const fixture = TestBed.createComponent(Host);
    fixture.detectChanges();
    await fixture.whenStable();
    await new Promise((resolve) => setTimeout(resolve, 0)); // let promise callbacks settle
    fixture.detectChanges();
    return fixture;
  }

  it('creates one chart in its container and draws the candles it was given', async () => {
    const fixture = await setup();

    expect(created).toHaveLength(1);
    expect(chart.drawn).toHaveLength(1);
    expect(chart.drawn[0].data.candles.map((c) => c.close)).toEqual([1, 2, 3]);
    expect(chart.drawn[0].resetView).toBe(true);
    expect((fixture.nativeElement as HTMLElement).contains(created[0])).toBe(true);
  });

  it('exposes an accessible name for the graphic', async () => {
    const fixture = await setup();
    const host = (fixture.nativeElement as HTMLElement).querySelector('[role="img"]');

    expect(host?.getAttribute('aria-label')).toBe('Gráfico de velas de prueba');
    fixture.componentInstance.label.set('Otro resumen');
    fixture.detectChanges();
    expect(host?.getAttribute('aria-label')).toBe('Otro resumen');
  });

  it('keeps the view when the same series gets more candles (older ones loaded)', async () => {
    const fixture = await setup();

    fixture.componentInstance.data.set(data([0, 1, 2, 3]));
    fixture.detectChanges();
    await fixture.whenStable();

    expect(chart.drawn).toHaveLength(2);
    expect(chart.drawn[1].data.candles).toHaveLength(4);
    expect(chart.drawn[1].resetView).toBe(false);
  });

  it('fits the view again when the series itself changes', async () => {
    const fixture = await setup();

    fixture.componentInstance.key.set('B');
    fixture.componentInstance.data.set(data([9, 8]));
    fixture.detectChanges();
    await fixture.whenStable();

    const last = chart.drawn.at(-1);
    expect(last?.resetView).toBe(true);
    expect(last?.data.candles.map((c) => c.close)).toEqual([9, 8]);
  });

  it('releases the chart when it is destroyed', async () => {
    const fixture = await setup();
    fixture.destroy();
    expect(chart.destroyed).toBe(1);
  });

  it('releases a chart that finished loading after the component was gone', async () => {
    let resolve!: (handle: ChartHandle) => void;
    const fixture = await setup(() => new Promise<ChartHandle>((r) => (resolve = r)));

    fixture.destroy();
    resolve(chart);
    await Promise.resolve();

    expect(chart.destroyed).toBe(1);
    expect(chart.drawn).toHaveLength(0);
  });

  it('says so, and points to the table, when the drawing library cannot load', async () => {
    const fixture = await setup(() => Promise.reject(new Error('chunk failed')));
    const element = fixture.nativeElement as HTMLElement;

    const alert = element.querySelector('[role="alert"]');
    expect(alert?.textContent).toContain('No se pudo cargar el gráfico');
    expect(alert?.textContent).toContain('tabla');
    expect(element.querySelector('.chart--hidden')).not.toBeNull();
  });
});
