import { Component } from '@angular/core';

interface DrawnCandle {
  x: number;
  wickTop: number;
  wickBottom: number;
  bodyTop: number;
  bodyHeight: number;
  rising: boolean;
}

// A hand-made shape, NOT market data: closing levels chosen only to look like a
// chart, rescaled to fill the frame. The figure is labelled as an illustration.
const CLOSES: readonly number[] = [
  70, 66, 69, 61, 64, 55, 59, 51, 56, 47, 52, 43, 49, 38, 45, 36, 41, 31, 38, 28, 34, 24, 30, 20,
];
const START = 74;
const LOW = Math.min(...CLOSES);
const HIGH = Math.max(START, ...CLOSES);
const SHAPE: readonly (readonly [number, number])[] = CLOSES.map((close, index) => [
  ((index === 0 ? START : CLOSES[index - 1]) - LOW) / (HIGH - LOW),
  (close - LOW) / (HIGH - LOW),
]);

const WIDTH = 320;
const HEIGHT = 150;
const STEP = WIDTH / SHAPE.length;

const CANDLES: readonly DrawnCandle[] = SHAPE.map(([open, close], index) => {
  const top = Math.min(open, close);
  const bottom = Math.max(open, close);
  const scale = (value: number) => 14 + value * (HEIGHT - 28);
  return {
    x: index * STEP + STEP / 2,
    wickTop: scale(Math.max(top - 0.05, 0)),
    wickBottom: scale(Math.min(bottom + 0.05, 1)),
    bodyTop: scale(top),
    bodyHeight: Math.max(scale(bottom) - scale(top), 3),
    // Chart y grows downwards: a smaller close means the price moved up.
    rising: close < open,
  };
});

/** Decorative picture of the explorer for the hero. It is an ILLUSTRATION and says
 * so on its face: it must never look like real, current market data. */
@Component({
  selector: 'app-hero-preview',
  template: `
    <figure class="preview">
      <div class="window" aria-hidden="true">
        <div class="bar">
          <span class="dots"><i></i><i></i><i></i></span>
          <span class="pair">BTC/USDT · 1m</span>
          <span class="chip chip--gold">Ilustración</span>
        </div>

        <svg class="chart" [attr.viewBox]="'0 0 ' + width + ' ' + height" role="presentation">
          @for (line of gridLines; track line) {
            <line class="grid" x1="0" [attr.y1]="line" [attr.x2]="width" [attr.y2]="line" />
          }
          @for (candle of candles; track candle.x) {
            <line
              class="wick"
              [class.wick--up]="candle.rising"
              [attr.x1]="candle.x"
              [attr.x2]="candle.x"
              [attr.y1]="candle.wickTop"
              [attr.y2]="candle.wickBottom"
            />
            <rect
              class="body"
              [class.body--up]="candle.rising"
              [attr.x]="candle.x - 4"
              [attr.y]="candle.bodyTop"
              width="8"
              [attr.height]="candle.bodyHeight"
              rx="1"
            />
          }
        </svg>

        <div class="status">
          <span class="chip chip--success"><span>✓</span> Al día</span>
          <span class="chip chip--success"><span>✓</span> Calidad correcta</span>
          <span class="chip">Fuente · Binance</span>
          <span class="chip">UTC</span>
        </div>
      </div>
      <figcaption>Ilustración del explorador de mercado. No muestra datos reales.</figcaption>
    </figure>
  `,
  styles: `
    :host {
      display: block;
    }

    .preview {
      margin: 0;
    }

    .window {
      overflow: hidden;
      background: var(--freyja-card-bg);
      border: 1px solid var(--freyja-border);
      border-radius: var(--freyja-radius-lg);
      box-shadow: var(--freyja-shadow-raised), var(--freyja-glow-brand);
    }

    .bar {
      display: flex;
      align-items: center;
      gap: var(--freyja-space-3);
      padding: var(--freyja-space-3) var(--freyja-space-4);
      border-bottom: 1px solid var(--freyja-border-subtle);
    }

    .dots {
      display: inline-flex;
      gap: 0.35rem;

      i {
        width: 0.6rem;
        height: 0.6rem;
        background: var(--freyja-border-subtle);
        border-radius: var(--freyja-radius-full);
      }
    }

    .pair {
      flex: 1;
      color: var(--freyja-text-cream);
      font-family: var(--freyja-font-mono);
      font-size: var(--freyja-text-size-sm);
    }

    .chart {
      display: block;
      width: 100%;
      padding: var(--freyja-space-4);
    }

    .grid {
      stroke: var(--freyja-border-subtle);
      stroke-width: 1;
    }

    .wick {
      stroke: var(--freyja-market-down);
      stroke-width: 1.5;
    }

    .wick--up {
      stroke: var(--freyja-market-up);
    }

    /* Falling candles are filled, rising ones hollow: not colour alone. */
    .body {
      fill: var(--freyja-market-down);
      stroke: var(--freyja-market-down);
    }

    .body--up {
      fill: var(--freyja-card-bg);
      stroke: var(--freyja-market-up);
      stroke-width: 1.5;
    }

    .status {
      display: flex;
      flex-wrap: wrap;
      gap: var(--freyja-space-2);
      padding: var(--freyja-space-3) var(--freyja-space-4) var(--freyja-space-4);
      border-top: 1px solid var(--freyja-border-subtle);
    }

    figcaption {
      margin-top: var(--freyja-space-3);
      color: var(--freyja-text-muted);
      font-size: var(--freyja-text-size-xs);
      text-align: center;
    }
  `,
})
export class HeroPreview {
  protected readonly width = WIDTH;
  protected readonly height = HEIGHT;
  protected readonly candles = CANDLES;
  protected readonly gridLines = [30, 60, 90, 120];
}
