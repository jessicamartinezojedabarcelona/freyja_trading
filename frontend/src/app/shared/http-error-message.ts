import { HttpErrorResponse } from '@angular/common/http';

const NETWORK_ERROR_MESSAGE =
  'No se pudo conectar con el servidor. Comprueba tu conexión e inténtalo de nuevo.';

/** Turns an unexpected HTTP failure into a human, non-technical message.
 * Never surfaces raw browser/network text (e.g. "Failed to fetch") or any
 * other internal detail to the user. */
export function humanizeUnexpectedError(error: HttpErrorResponse, fallback: string): string {
  if (error.status === 0) {
    return NETWORK_ERROR_MESSAGE;
  }
  return fallback;
}
