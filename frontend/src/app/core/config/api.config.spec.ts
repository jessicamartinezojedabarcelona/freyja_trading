import { API_BASE_URL } from './api.config';
import { environment } from '../../../environments/environment';
import { environment as prodEnvironment } from '../../../environments/environment.prod';

describe('API_BASE_URL', () => {
  it('is sourced from the environment file, not a hardcoded literal', () => {
    expect(API_BASE_URL).toBe(environment.apiBaseUrl);
  });

  it('uses the development backend URL when built with the default (non-production) config', () => {
    // ng test always uses environment.ts, never environment.prod.ts's
    // fileReplacement — this pins that assumption so a change to angular.json
    // that accidentally swapped it in for tests would be caught here.
    expect(API_BASE_URL).toBe('http://localhost:8000/api/v1');
  });
});

describe('environment.prod.ts', () => {
  it('is flagged as production', () => {
    expect(prodEnvironment.production).toBe(true);
  });

  it('does not point at the local development backend', () => {
    expect(prodEnvironment.apiBaseUrl).not.toContain('localhost');
    expect(prodEnvironment.apiBaseUrl).not.toContain('127.0.0.1');
  });

  it('uses HTTPS, not a plain-HTTP URL', () => {
    expect(prodEnvironment.apiBaseUrl.startsWith('https://')).toBe(true);
  });

  it('contains no value that looks like a real secret or credential', () => {
    expect(prodEnvironment.apiBaseUrl).not.toMatch(/[:@].*[:@]/);
  });
});
