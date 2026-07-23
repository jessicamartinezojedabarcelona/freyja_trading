// PENDING: this is a placeholder, overwritten automatically at build time by
// scripts/generate-production-environment.mjs (now a mandatory prerequisite
// of `npm run build` itself — see package.json), which computes the real
// value from FREYJA_BACKEND_URL (RENDER_EXTERNAL_URL of the backend service,
// injected via fromService in render.yaml on a real Render build, or an
// .invalid placeholder domain injected only as a CI env var — never
// hardcoded here or in the generator script). If you are seeing this exact
// placeholder in a deployed bundle, something is deeply wrong: `npm run
// build` cannot succeed without the generator running first, and the
// generator refuses to write this exact placeholder text. This file is
// picked up only for the Angular "production" build configuration via
// fileReplacements in angular.json; `environment.ts` (this constant's dev
// counterpart) is used everywhere else, including `ng test`.
export const environment = {
  production: true,
  apiBaseUrl: 'https://REPLACE_WITH_RENDER_BACKEND_URL/api/v1',
};
