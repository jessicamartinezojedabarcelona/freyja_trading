import {
  DataQuality,
  FreshnessStatus,
  QualityIssueCode,
} from '../../core/market-data/market-data.models';

// Human wording for every state the API can report. The backend's own `detail`
// strings are technical (English) and are never shown; each code maps here.
// Every state pairs a symbol and text with its colour: colour alone never
// carries meaning (UX-DESIGN-SYSTEM-001 §12).

export const ISSUE_LABELS: Record<QualityIssueCode, string> = {
  OPEN_CANDLE_EXCLUDED: 'Se excluyó la vela en curso: aún no ha cerrado.',
  DUPLICATE_DROPPED: 'El proveedor repitió alguna vela; se descartaron los duplicados.',
  OUT_OF_ORDER: 'El proveedor envió velas desordenadas; se reordenaron.',
  GAP: 'Faltan velas dentro del periodo mostrado.',
  INCOMPLETE_RANGE: 'El periodo pedido no está completo: faltan velas al principio o al final.',
  STALE: 'Los datos están desactualizados: falta alguna de las velas más recientes.',
  INSTRUMENT_NOT_TRADING: 'El proveedor indica que el instrumento no está operativo ahora.',
  REVISED_CANDLE:
    'El proveedor informa valores distintos de los guardados para alguna vela. Se conservan los guardados.',
  PROVIDER_FAILING:
    'El último intento de actualizar esta serie falló: puede haber velas más recientes que las mostradas.',
  RATE_LIMITED: 'El proveedor limitó las peticiones.',
  TIMEOUT: 'El proveedor tardó demasiado en responder.',
  PROVIDER_ERROR: 'El proveedor devolvió un error.',
  INVALID_RESPONSE: 'El proveedor devolvió datos no válidos, que se descartaron.',
  SYMBOL_MISMATCH: 'El símbolo del proveedor no coincide con el del catálogo.',
  NO_DATA: 'Todavía no hay velas guardadas para esta serie.',
};

export function issueLabel(code: string): string {
  return (
    (ISSUE_LABELS as Record<string, string | undefined>)[code] ??
    `Incidencia de calidad de datos (${code}).`
  );
}

export interface StatusPresentation {
  icon: string;
  text: string;
  /** Semantic token suffix: success, info, warning, error, blocked. */
  tone: 'success' | 'info' | 'warning' | 'error' | 'blocked';
}

export const QUALITY_PRESENTATION: Record<DataQuality, StatusPresentation> = {
  OK: { icon: '✓', text: 'Calidad correcta', tone: 'success' },
  DEGRADED: { icon: '⚠', text: 'Calidad degradada', tone: 'warning' },
  UNAVAILABLE: { icon: '✕', text: 'Datos no disponibles', tone: 'error' },
};

/** How the last refresh attempt of the source went, worded for that context
 * (the series quality wording does not fit: "quality" is not what an attempt has). */
export const PROVIDER_PRESENTATION: Record<DataQuality, StatusPresentation> = {
  OK: { icon: '✓', text: 'correcto', tone: 'success' },
  DEGRADED: { icon: '⚠', text: 'con incidencias', tone: 'warning' },
  UNAVAILABLE: { icon: '✕', text: 'falló', tone: 'error' },
};

export const FRESHNESS_PRESENTATION: Record<FreshnessStatus, StatusPresentation> = {
  FRESH: { icon: '✓', text: 'Al día', tone: 'success' },
  STALE: { icon: '⚠', text: 'Desactualizado', tone: 'warning' },
  NO_DATA: { icon: 'ⓘ', text: 'Sin datos', tone: 'info' },
};
