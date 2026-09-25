import {
  CandlestickSeries,
  ColorType,
  CrosshairMode,
  HistogramSeries,
  createChart,
  type Time,
  type UTCTimestamp,
} from 'lightweight-charts';

import { ChartData, axisTickLabel, crosshairLabel, followLatest } from './chart-data';
import { ChartHandle, ChartOptions } from './chart-handle';

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

/** The library hands times back as the numbers it was given (seconds since the epoch). */
const seconds = (time: Time): number =>
  typeof time === 'number' ? time : Date.parse(String(time)) / 1000;

export async function createLightweightChart(
  host: HTMLElement,
  options: ChartOptions,
): Promise<ChartHandle> {
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
    // Times are instants (UTC seconds); the library would print them in UTC, so both the
    // axis and the crosshair are written in the zone of the person instead.
    localization: {
      timeFormatter: (time: Time) => crosshairLabel(seconds(time), options.timeZone),
    },
    timeScale: {
      borderColor: border,
      timeVisible: true,
      secondsVisible: false,
      tickMarkFormatter: (time: Time, tickType: number) =>
        axisTickLabel(seconds(time), tickType, options.timeZone),
    },
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

  let lastDrawn: number | null = null;

  return {
    setData(data: ChartData, drawOptions: { resetView: boolean }): void {
      const visible = drawOptions.resetView ? null : chart.timeScale().getVisibleRange();
      const keptRange = followLatest(
        visible === null ? null : { from: seconds(visible.from), to: seconds(visible.to) },
        lastDrawn,
        data.candles.at(-1)?.time ?? null,
      );
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
      lastDrawn = data.candles.at(-1)?.time ?? null;
      if (keptRange !== null) {
        chart.timeScale().setVisibleRange({
          from: keptRange.from as UTCTimestamp,
          to: keptRange.to as UTCTimestamp,
        });
      } else {
        chart.timeScale().fitContent();
      }
    },
    destroy(): void {
      chart.remove();
    },
  };
}
