# ADR 0005 — Librería del gráfico de velas del explorador de mercado

- **Estado:** Accepted (decisión técnica de arquitectura, CLAUDE.md §1 y §3)
- **Fecha:** 2026-09-24
- **Tarea:** MARKET-DATA-EXPLORER-001
- **Relacionado:** ADR 0004 (explorador y tiempo real)

## Contexto

MARKET-DATA-EXPLORER-001 prohíbe incorporar una librería de gráficos sin
aprobación arquitectónica. El explorador debe dibujar velas cerradas y su
volumen, permitir desplazarse hacia atrás en el histórico, y más adelante
actualizar la última vela y marcar señales (ADR 0004). Dibujarlo a mano sobre
`canvas` o SVG supone reimplementar ejes, escalas de tiempo, zoom, cursor y
rendimiento con miles de velas.

## Decisión

Se usa **`lightweight-charts` 5.2.1** (TradingView), fijada a versión exacta.

- **Licencia:** Apache-2.0, compatible con el proyecto. Exige mostrar la
  atribución a TradingView: el explorador enlaza «TradingView Lightweight
  Charts™» bajo el gráfico y no oculta el logotipo de la librería.
- **Tamaño y carga:** unos 45 KB. Se carga **de forma diferida** (`import()`
  dinámico) solo al abrir un instrumento, así que no pesa en la portada, el
  acceso ni el resto de la aplicación.
- **Aislamiento:** el resto del código no conoce la librería. El componente
  `CandleChart` la usa detrás de la interfaz `ChartHandle` y de un token de
  inyección (`CHART_FACTORY`); las pruebas usan un doble de esa interfaz y
  ninguna prueba depende del canvas.
- **Datos exactos:** la API entrega precios y volúmenes como **texto decimal
  exacto**. Solo en el borde de dibujo se convierten a `number`; nada de lo que
  se calcula para decidir (estado de la última vela, subida o bajada) usa
  coma flotante — se compara por dígitos exactos (CLAUDE.md §6). El navegador no
  calcula ninguna señal.
- **Zona horaria:** el eje muestra UTC y así se declara junto al gráfico.
- **Accesibilidad:** el gráfico es un canvas y no lo leen los lectores de
  pantalla; por eso lleva una descripción textual y una **tabla alternativa**
  con las últimas 20 velas, con los valores exactos de la API. Subida/bajada se
  distinguen por forma (vela hueca/rellena) y texto, no solo por color.

## Alternativas descartadas

- **Dibujo propio en canvas/SVG:** coste alto y riesgo de errores de escala y
  de tiempo, sin ventaja de producto.
- **ECharts / Chart.js / Highcharts:** más pesadas, no especializadas en series
  financieras (Highcharts Stock exige licencia de pago).
- **Widget incrustado de TradingView:** carga datos de TradingView, no los de
  Freyja; contradice «solo datos reales del endpoint propio».

## Consecuencias

- Una dependencia externa más que mantener; al estar acotada tras `ChartHandle`,
  sustituirla afecta a un solo archivo.
- Si se necesitaran indicadores o dibujos propios (fuera de esta tarea), se
  reevaluará en un ADR nuevo.
