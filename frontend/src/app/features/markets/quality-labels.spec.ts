import { QualityIssueCode } from '../../core/market-data/market-data.models';
import {
  FRESHNESS_PRESENTATION,
  ISSUE_LABELS,
  QUALITY_PRESENTATION,
  issueLabel,
} from './quality-labels';

// Every code the backend can emit (domain.market_data.QualityIssueCode).
const BACKEND_CODES: QualityIssueCode[] = [
  'OPEN_CANDLE_EXCLUDED',
  'DUPLICATE_DROPPED',
  'OUT_OF_ORDER',
  'GAP',
  'INCOMPLETE_RANGE',
  'STALE',
  'INSTRUMENT_NOT_TRADING',
  'REVISED_CANDLE',
  'PROVIDER_FAILING',
  'RATE_LIMITED',
  'TIMEOUT',
  'PROVIDER_ERROR',
  'INVALID_RESPONSE',
  'SYMBOL_MISMATCH',
  'NO_DATA',
];

describe('quality labels', () => {
  it('explains every backend issue code in Spanish', () => {
    expect(Object.keys(ISSUE_LABELS).sort()).toEqual([...BACKEND_CODES].sort());
    for (const code of BACKEND_CODES) {
      expect(issueLabel(code).length, code).toBeGreaterThan(10);
      expect(issueLabel(code), code).not.toContain(code); // no raw code leaks to the user
    }
  });

  it('never shows the backend detail text, and names an unknown code plainly', () => {
    expect(issueLabel('SOMETHING_NEW')).toContain('SOMETHING_NEW');
    expect(issueLabel('SOMETHING_NEW')).toContain('Incidencia');
  });

  it('pairs every state with a symbol and a text, so colour is never the only signal', () => {
    for (const presentation of [
      ...Object.values(QUALITY_PRESENTATION),
      ...Object.values(FRESHNESS_PRESENTATION),
    ]) {
      expect(presentation.icon.length).toBeGreaterThan(0);
      expect(presentation.text.length).toBeGreaterThan(0);
    }
  });

  it('gives each quality level a distinct symbol', () => {
    const icons = Object.values(QUALITY_PRESENTATION).map((p) => p.icon);
    expect(new Set(icons).size).toBe(icons.length);
  });
});
