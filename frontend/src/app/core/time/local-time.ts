import { InjectionToken } from '@angular/core';

/**
 * Time is UTC everywhere except in front of the person: the API, the database, the URL and
 * every query stay UTC, and only what is *shown* is converted, to the zone of the browser.
 * The zone is always printed next to a local time, so a time is never shown without saying
 * which one it is.
 */

/** The IANA zone the browser is in (e.g. "Europe/Madrid"), or "UTC" if it cannot say. */
export function browserTimeZone(): string {
  try {
    const zone = Intl.DateTimeFormat().resolvedOptions().timeZone;
    return zone !== undefined && zone !== '' && isValidTimeZone(zone) ? zone : 'UTC';
  } catch {
    return 'UTC';
  }
}

export function isValidTimeZone(zone: string): boolean {
  try {
    new Intl.DateTimeFormat('es-ES', { timeZone: zone });
    return true;
  } catch {
    return false;
  }
}

/** Injectable so any zone can be tested, and a "choose my zone" setting could provide it. */
export const USER_TIME_ZONE = new InjectionToken<string>('USER_TIME_ZONE', {
  providedIn: 'root',
  factory: () => browserTimeZone(),
});

const formats = new Map<string, Intl.DateTimeFormat>();

function format(
  zone: string,
  key: string,
  options: Intl.DateTimeFormatOptions,
): Intl.DateTimeFormat {
  const id = `${zone}|${key}`;
  let cached = formats.get(id);
  if (cached === undefined) {
    cached = new Intl.DateTimeFormat('es-ES', {
      ...options,
      timeZone: safeZone(zone),
      hourCycle: 'h23',
    });
    formats.set(id, cached);
  }
  return cached;
}

function safeZone(zone: string): string {
  return isValidTimeZone(zone) ? zone : 'UTC';
}

const DATE_TIME: Intl.DateTimeFormatOptions = {
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
  second: '2-digit',
};

/** "25/09/2026, 19:41:00 GMT+2" for an ISO instant; the zone is always explicit. */
export function formatInstant(iso: string | null, zone: string): string {
  if (iso === null) return '—';
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return '—';
  return `${format(zone, 'datetime', DATE_TIME).format(date)} ${zoneAbbreviation(zone, date)}`;
}

/** "19:45:12", the wall clock in the zone (no zone printed: the page already states it). */
export function formatClock(date: Date, zone: string): string {
  return format(zone, 'clock', { hour: '2-digit', minute: '2-digit', second: '2-digit' }).format(
    date,
  );
}

/** "GMT+2", "GMT-5" or "UTC": the offset that applied in that zone at that instant. The offset
 * (not a name like CEST, which changes with the browser's language) says exactly which time it is. */
export function zoneAbbreviation(zone: string, at: Date): string {
  const name = safeZone(zone);
  if (name === 'UTC') return 'UTC';
  const part = format(name, 'zone', { timeZoneName: 'shortOffset' })
    .formatToParts(at)
    .find((p) => p.type === 'timeZoneName');
  return part?.value ?? name;
}

/** "Europe/Madrid, GMT+2": the zone by name and by offset, for a note next to a chart. */
export function zoneLabel(zone: string, at: Date): string {
  const name = safeZone(zone);
  const abbreviation = zoneAbbreviation(name, at);
  return name === 'UTC' ? 'UTC' : `${name}, ${abbreviation}`;
}
