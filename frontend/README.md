# Freyja 2.0 — Frontend

Scaffold mínimo, reproducible y accesible del frontend de Freyja 2.0, generado con Angular CLI 22.0.7.

Esta fase contiene únicamente la fundación técnica de la aplicación. Todavía no incluye dashboard, conexión con el backend ni funcionalidad de trading.

## Requisitos

- Node.js 24 LTS.
- npm 11.
- Dependencias instaladas mediante el lockfile versionado.

## Instalación reproducible

Desde `frontend/`:

```bash
npm ci
```

## Desarrollo local

```bash
npm start
```

El servidor de desarrollo utiliza la configuración de Angular y se inicia en `http://localhost:4200/` de forma predeterminada.

## Build de producción

```bash
npm run build
```

Los artefactos generados se almacenan en `dist/` y no se versionan.

## Lint

```bash
npm run lint
```

## Tests unitarios

Ejecución única y no interactiva:

```bash
npm test -- --watch=false
```

## Seguridad de dependencias

El proyecto fija Vite 7.3.6 mediante `overrides` para utilizar una versión corregida y deduplicada de esbuild 0.28.1.

La auditoría debe mantenerse limpia:

```bash
npm audit
```

## Capacidades no incluidas

Este scaffold no incluye:

- pruebas E2E;
- dashboard funcional;
- autenticación;
- conexión con APIs;
- datos de mercado;
- señales o estrategias;
- ejecución DEMO o REAL.

Las capacidades posteriores se implementarán únicamente mediante tareas autorizadas y revisadas por el Arquitecto.
