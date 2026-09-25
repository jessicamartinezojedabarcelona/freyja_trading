import {
  browserTimeZone,
  formatClock,
  formatInstant,
  isValidTimeZone,
  zoneAbbreviation,
  zoneLabel,
} from './local-time';

// 2026-09-25 17:41:07 UTC: summer time in Madrid (GMT+2), Bogota is always GMT-5.
const SUMMER = '2026-09-25T17:41:07Z';
const WINTER = '2026-01-15T17:41:07Z';

describe('formatInstant', () => {
  it('writes the time as it is on the clock of the person, with no offset to read wrongly', () => {
    expect(formatInstant(SUMMER, 'Europe/Madrid')).toBe('25/09/2026, 19:41:07');
    expect(formatInstant(SUMMER, 'America/Bogota')).toBe('25/09/2026, 12:41:07');
    expect(formatInstant(SUMMER, 'UTC')).toBe('25/09/2026, 17:41:07');
    expect(formatInstant(SUMMER, 'Europe/Madrid')).not.toMatch(/GMT|UTC/);
  });

  it('applies the offset that was in force at that instant (daylight saving)', () => {
    // The same UTC hour is one hour apart from summer to winter in Madrid.
    expect(formatInstant(WINTER, 'Europe/Madrid')).toBe('15/01/2026, 18:41:07');
    expect(formatInstant(SUMMER, 'Europe/Madrid')).toBe('25/09/2026, 19:41:07');
  });

  it('follows a change of day and never prints 24:00', () => {
    expect(formatInstant('2026-09-24T23:30:00Z', 'Europe/Madrid')).toBe('25/09/2026, 01:30:00');
    expect(formatInstant('2026-09-25T00:00:00Z', 'UTC')).toBe('25/09/2026, 00:00:00');
    expect(formatInstant('2026-09-24T22:00:00Z', 'Europe/Madrid')).toBe('25/09/2026, 00:00:00');
  });

  it('shows a dash for a missing or unreadable instant', () => {
    expect(formatInstant(null, 'UTC')).toBe('—');
    expect(formatInstant('garbage', 'UTC')).toBe('—');
  });

  it('falls back to UTC when the zone is not real', () => {
    expect(formatInstant(SUMMER, 'Not/AZone')).toBe('25/09/2026, 17:41:07');
  });

  it('is the same instant however it is written (the API is UTC, an offset is equal)', () => {
    expect(formatInstant('2026-09-25T19:41:07+02:00', 'Europe/Madrid')).toBe(
      formatInstant(SUMMER, 'Europe/Madrid'),
    );
  });
});

describe('formatClock', () => {
  it('is the wall clock of the zone, with seconds', () => {
    const at = new Date(SUMMER);
    expect(formatClock(at, 'Europe/Madrid')).toBe('19:41:07');
    expect(formatClock(at, 'America/Bogota')).toBe('12:41:07');
  });
});

describe('zoneLabel', () => {
  it('names the zone and its offset', () => {
    expect(zoneLabel('Europe/Madrid', new Date(SUMMER))).toBe('Europe/Madrid, GMT+2');
    expect(zoneLabel('Europe/Madrid', new Date(WINTER))).toBe('Europe/Madrid, GMT+1');
    expect(zoneLabel('America/Bogota', new Date(SUMMER))).toBe('America/Bogota, GMT-5');
    expect(zoneLabel('UTC', new Date(SUMMER))).toBe('UTC');
    expect(zoneAbbreviation('UTC', new Date(SUMMER))).toBe('UTC');
  });

  it('does not invent a zone that does not exist', () => {
    expect(zoneLabel('Not/AZone', new Date(SUMMER))).toBe('UTC');
  });
});

describe('the browser zone', () => {
  it('is a real zone, or UTC', () => {
    expect(isValidTimeZone(browserTimeZone())).toBe(true);
  });

  it('recognises real and unreal zones', () => {
    expect(isValidTimeZone('Europe/Madrid')).toBe(true);
    expect(isValidTimeZone('UTC')).toBe(true);
    expect(isValidTimeZone('Mars/Olympus')).toBe(false);
    expect(isValidTimeZone('')).toBe(false);
  });
});
