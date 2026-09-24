import { HttpParams } from '@angular/common/http';

export type ParamValue = string | number | boolean | undefined;

/** Only sets a param when its value is actually provided — an omitted
 * filter must never be sent as the literal string "undefined". */
export function buildParams(entries: Record<string, ParamValue>): HttpParams {
  let params = new HttpParams();
  for (const [key, value] of Object.entries(entries)) {
    if (value !== undefined) {
      params = params.set(key, String(value));
    }
  }
  return params;
}
