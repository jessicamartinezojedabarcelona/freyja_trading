import { writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

// Pure validation/computation, exported so it can be unit-tested directly
// (see generate-production-environment.spec.ts) without touching the
// filesystem or process.env.
export function computeApiBaseUrl(backendUrl) {
  if (!backendUrl || !backendUrl.trim()) {
    throw new Error(
      'FREYJA_BACKEND_URL no está definida. Render debe inyectarla mediante ' +
        'fromService (envVarKey: RENDER_EXTERNAL_URL) apuntando al backend.',
    );
  }

  const trimmed = backendUrl.trim();

  if (!trimmed.startsWith('https://')) {
    throw new Error(`FREYJA_BACKEND_URL debe usar HTTPS. Valor recibido: "${trimmed}"`);
  }

  const lower = trimmed.toLowerCase();
  if (lower.includes('localhost') || lower.includes('127.0.0.1')) {
    throw new Error(
      `FREYJA_BACKEND_URL no puede apuntar a localhost en un build de producción. Valor recibido: "${trimmed}"`,
    );
  }

  if (lower.includes('replace_with') || lower.includes('placeholder')) {
    throw new Error(
      `FREYJA_BACKEND_URL parece un valor de plantilla sin sustituir. Valor recibido: "${trimmed}"`,
    );
  }

  return `${trimmed.replace(/\/+$/, '')}/api/v1`;
}

export function renderEnvironmentFileContents(apiBaseUrl) {
  return `// Generado automáticamente durante el build de Render a partir de
// FREYJA_BACKEND_URL (RENDER_EXTERNAL_URL del backend, vía fromService en
// render.yaml). No edites este archivo a mano: cualquier edición manual se
// sobrescribe en el siguiente build de Render. Ver
// frontend/scripts/generate-production-environment.mjs y README §19.
export const environment = {
  production: true,
  apiBaseUrl: '${apiBaseUrl}',
};
`;
}

function main() {
  const apiBaseUrl = computeApiBaseUrl(process.env.FREYJA_BACKEND_URL);
  const scriptDir = dirname(fileURLToPath(import.meta.url));
  const outPath = join(scriptDir, '..', 'src', 'environments', 'environment.prod.ts');
  writeFileSync(outPath, renderEnvironmentFileContents(apiBaseUrl), 'utf-8');
  console.log(`environment.prod.ts generado con apiBaseUrl=${apiBaseUrl}`);
}

const isDirectCliInvocation =
  process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href;

if (isDirectCliInvocation) {
  try {
    main();
  } catch (error) {
    console.error(`generate-production-environment.mjs: ${error.message}`);
    process.exit(1);
  }
}
