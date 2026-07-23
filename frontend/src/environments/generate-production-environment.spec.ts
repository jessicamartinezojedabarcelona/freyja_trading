// This spec lives under src/ (so Angular's test runner and tsconfig.spec.json
// discover it) but exercises the pure functions of a plain Node script that
// lives outside src/ — frontend/scripts/generate-production-environment.mjs,
// invoked only by Render's build (see render.yaml), never by `ng build`/`ng
// test` themselves.
import {
  computeApiBaseUrl,
  renderEnvironmentFileContents,
  // @ts-expect-error -- plain .mjs, no type declarations, imported for its
  // runtime exports only.
} from '../../scripts/generate-production-environment.mjs';

describe('computeApiBaseUrl', () => {
  it('appends /api/v1 to a valid HTTPS backend URL', () => {
    expect(computeApiBaseUrl('https://freyja-backend.onrender.com')).toBe(
      'https://freyja-backend.onrender.com/api/v1',
    );
  });

  it('strips a trailing slash before appending /api/v1', () => {
    expect(computeApiBaseUrl('https://freyja-backend.onrender.com/')).toBe(
      'https://freyja-backend.onrender.com/api/v1',
    );
  });

  it('throws when the value is missing', () => {
    expect(() => computeApiBaseUrl(undefined)).toThrow(/no está definida/);
    expect(() => computeApiBaseUrl('')).toThrow(/no está definida/);
  });

  it('throws when the value uses plain HTTP', () => {
    expect(() => computeApiBaseUrl('http://freyja-backend.onrender.com')).toThrow(/HTTPS/);
  });

  it('throws when the value points at localhost', () => {
    expect(() => computeApiBaseUrl('https://localhost:8000')).toThrow(/localhost/);
  });

  it('throws when the value points at 127.0.0.1', () => {
    expect(() => computeApiBaseUrl('https://127.0.0.1:8000')).toThrow(/localhost/);
  });

  it('throws when the value still contains the committed placeholder text', () => {
    expect(() => computeApiBaseUrl('https://REPLACE_WITH_RENDER_BACKEND_URL')).toThrow(/plantilla/);
  });
});

describe('renderEnvironmentFileContents', () => {
  it('embeds the computed apiBaseUrl and marks production true', () => {
    const contents = renderEnvironmentFileContents('https://freyja-backend.onrender.com/api/v1');
    expect(contents).toContain('production: true');
    expect(contents).toContain("apiBaseUrl: 'https://freyja-backend.onrender.com/api/v1'");
  });
});
