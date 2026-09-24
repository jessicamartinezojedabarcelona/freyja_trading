import {
  CandlestickSeries,
  ColorType,
  CrosshairMode,
  HistogramSeries,
  createChart,
  type UTCTimestamp,
} from 'lightweight-charts';

import { ChartData } from './chart-data';
import { ChartHandle } from './chart-handle';

// Drawing adapter over TradingView's lightweight-charts (Apache-2.0). Its
// licence requires the attribution the page shows next to the chart.
//
// Direction is never carried by colour alone (UX-DESIGN-SYSTEM-001 §16): rising
// candles are drawn HOLLOW and falling candles FILLED, in addition to the
// market-up / market-down tokens.

const FALLBACKS = {
  up: '#8fd2ab',
  down: '#e26a8a',
  text: '#f1ead9',
  muted: '#9c9578',
  grid: 'rgba(241, 234, 217, 0.08)',
};

function token(name: string, fallback: string): string {
  const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return value === '' ? fallback : value;
}

const HOLLOW = 'rgba(0, 0, 0, 0)';

export async function createLightweightChart(host: HTMLElement): Promise<ChartHandle> {
  const up = token('--freyja-market-up', FALLBACKS.up);
  const down = token('--freyja-market-down', FALLBACKS.down);
  const text = token('--freyja-text-cream', FALLBACKS.text);
  const border = token('--freyja-border-subtle', FALLBACKS.grid);

  const chart = createChart(host, {
    autoSize: true,
    layout: {
      background: { type: ColorType.Solid, color: 'transparent' },
      textColor: text,
      attributionLogo: true,
    },
    grid: { vertLines: { color: border }, horzLines: { color: border } },
    rightPriceScale: { borderColor: border },
    timeScale: { borderColor: border, timeVisible: true, secondsVisible: false },
    crosshair: { mode: CrosshairMode.Normal },
  });

  const candles = chart.addSeries(CandlestickSeries, {
    upColor: HOLLOW,
    borderUpColor: up,
    wickUpColor: up,
    downColor: down,
    borderDownColor: down,
    wickDownColor: down,
  });
  const volume = chart.addSeries(HistogramSeries, {
    priceFormat: { type: 'volume' },
    priceScaleId: 'volume',
    lastValueVisible: false,
    priceLineVisible: false,
  });
  chart.priceScale('volume').applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } });

  return {
    setData(data: ChartData, options: { resetView: boolean }): void {
      const keptRange = options.resetView ? null : chart.timeScale().getVisibleRange();
      candles.applyOptions({
        priceFormat: {
          type: 'price',
          precision: data.precision,
          minMove: 1 / 10 ** data.precision,
        },
      });
      candles.setData(
        data.candles.map((candle) => ({
          time: candle.time as UTCTimestamp,
          open: candle.open,
          high: candle.high,
          low: candle.low,
          close: candle.close,
        })),
      );
      volume.setData(
        data.candles.map((candle) => ({
          time: candle.time as UTCTimestamp,
          value: candle.volume,
          color: candle.close >= candle.open ? `${up}66` : `${down}66`,
        })),
      );
      if (keptRange !== null) {
        chart.timeScale().setVisibleRange(keptRange);
      } else {
        chart.timeScale().fitContent();
      }
    },
    destroy(): void {
      chart.remove();
    },
  };
}
