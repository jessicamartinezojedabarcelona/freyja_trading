# UX-DESIGN-SYSTEM-001 — Sistema visual y componentes de Freyja 2.0

- **Estado:** En elaboración — entregado para auditoría independiente del
  Arquitecto. No implementado.
- **Fecha:** 2026-09-23
- **Tarea Notion:** [UX-DESIGN-SYSTEM-001 — Definir sistema visual y
  componentes](https://app.notion.com/p/3a14f4ea4dcc8130afedce6a4f8db635)
- **Orden del roadmap:** 2 de 3 (`UX-IA-001` ✅ → `UX-DESIGN-SYSTEM-001`
  → `UX-DASHBOARD-001`). Este documento no diseña el Dashboard, no
  implementa el shell ni ninguna pantalla y no modifica código.
- **Base:** [`UX-IA-001`](UX-IA-001-arquitectura-informacion-navegacion.md)
  (aprobado). El sitemap, las rutas y los estados de pantalla definidos
  allí no se modifican aquí.

## 1. Objetivo

Definir el sistema visual canónico de Freyja 2.0 —tokens, tipografía,
espaciado, semántica de estados, componentes base y reglas de
accesibilidad— para que todas las pantallas posteriores consuman una
única fuente de verdad y no aparezcan estilos, colores o componentes
duplicados o inconsistentes.

## 2. Inventario del estado actual del repositorio

Antes de definir nada se revisó lo que ya existe, para partir de ello en
vez de duplicarlo.

| Elemento | Ubicación | Estado |
|---|---|---|
| Tokens globales `--freyja-*` (14 variables: fondos, bordes, oro, texto, error, éxito, fuente serif) | `frontend/src/styles.scss` (`:root`) | Existen. Nacieron para la experiencia de autenticación. **Son la base canónica de este sistema** (§4). |
| Estilos de formulario, botón *submit*, errores, avisos, enlaces y divisor | `frontend/src/styles.scss`, bajo `.auth-page` | Existen, acotados a autenticación. Son la primera implementación *de facto* de inputs, botones y alertas. |
| Tarjeta con esquinas doradas, cabecera de marca, emblema | `frontend/src/app/shared/auth-shell/auth-shell.scss` | Existe, específica de autenticación. |
| Marca rúnica (fé) | `frontend/src/app/shared/rune-mark/` | Existe (`BRAND-RUNES-001`). SVG inline con `currentColor`. |
| Regla `prefers-reduced-motion` | `frontend/src/styles.scss` | Existe, solo para `.auth-page`. |
| Placeholder autenticado `HomePage` | `frontend/src/app/features/home/home.page.scss` | **Conflicto:** colores claros hardcodeados (`#ffffff`, `#1a1a1a`) y `system-ui`, sin usar ningún token (ver §18). |
| Librería UI, librería de iconos, librería de gráficos, webfonts | — | **No existen.** Dependencias de runtime: solo Angular, RxJS y tslib. |

## 3. Principios visuales

1. **Honestidad antes que estética.** Ningún recurso visual (color,
   animación, gráfico) puede sugerir datos, actividad o certeza que no
   existen. Un área sin datos se ve vacía y lo dice; nunca se decora con
   cifras o gráficos de ejemplo.
2. **Sobriedad profesional.** Tema oscuro de baja fatiga para sesiones
   largas de análisis. El oro de la marca es un acento, no un color de
   relleno: se reserva para marca, foco y acción principal.
3. **Legibilidad de datos primero.** Tablas y cifras priorizan alineación,
   cifras tabulares y jerarquía clara sobre ornamento.
4. **El estado nunca depende solo del color.** Todo estado semántico
   (éxito, error, bloqueado, DEMO, REAL, subida/bajada, nivel de riesgo)
   se comunica con al menos dos canales: color + texto, icono, forma o
   patrón.
5. **Una sola Freyja.** Un solo sistema visual para toda la aplicación.
   La profundidad de información puede variar por pantalla, pero no
   existen estilos "modo fácil" / "modo experto".
6. **Continuidad con la marca existente.** Se conserva la identidad ya
   integrada en autenticación (fondo casi negro azulado, oro, crema,
   marca rúnica) y se extiende; no se sustituye.

## 4. Fuente única de verdad

- **Todos los tokens se definen en un único lugar:** el bloque `:root` de
  `frontend/src/styles.scss`, que ya es hoy el único sitio con tokens. No
  se crea un segundo archivo de tokens ni un segundo prefijo.
- **Prefijo único:** `--freyja-`. Los 14 tokens existentes conservan su
  nombre y valor; este documento no renombra ninguno (renombrar es un
  cambio de código fuera de alcance; ver §19).
- **Los componentes solo consumen tokens.** Ningún estilo de componente o
  pantalla puede contener un valor de color hexadecimal, un tamaño de
  fuente o un espaciado "suelto" que no provenga de un token.
- **Componentes base compartidos, no por pantalla.** Los componentes de
  §14 viven en `frontend/src/app/shared/` (convención ya establecida por
  `auth-shell` y `rune-mark`). No se crean variantes de estilo específicas
  para una única pantalla.
- **Los estilos de `.auth-page` no se duplican.** Cuando se implementen
  los componentes genéricos de este documento, los estilos equivalentes
  de `.auth-page` deberán migrarse a ellos y retirarse en la misma tarea
  (CLAUDE.md §11). Esa migración **no** forma parte de esta tarea.
- **Ninguna librería UI** se incorpora sin decisión arquitectónica
  aprobada. Este sistema se define para implementarse con CSS/SCSS propio
  y componentes Angular *standalone*.

## 5. Arquitectura de tokens

Dos capas, ambas con el prefijo `--freyja-`:

1. **Valores base (primitivos):** los valores concretos de la paleta
   (p. ej. `--freyja-gold: #c9a24a`). Son los que cambian entre temas.
2. **Tokens semánticos:** describen un rol (`--freyja-status-error`,
   `--freyja-env-demo`, `--freyja-surface-raised`). Los componentes
   consumen **solo** tokens semánticos o, mientras no existan, los tokens
   existentes que ya cumplen ese rol.

Convención de nombres para los tokens nuevos:
`--freyja-<categoría>-<rol>[-<variante>]`, con categorías `surface`,
`text`, `border`, `status`, `env`, `market`, `risk`, `space`, `radius`,
`font`, `text-size`, `motion`, `focus`.

Para no romper nada ni duplicar, los tokens existentes cuyo nombre no
sigue esta convención (`--freyja-bg`, `--freyja-card-bg`,
`--freyja-text-cream`, etc.) siguen siendo válidos y se tratan como
tokens semánticos de pleno derecho. Un posible alias o renombrado queda
como decisión pendiente (§19).

## 6. Tema oscuro (tema inicial)

Contraste medido con la fórmula WCAG 2.x de luminancia relativa. Columna
"Contraste": sobre `--freyja-card-bg` (`#12141e`), la superficie más
habitual para contenido.

### 6.1 Superficies y bordes

| Token | Valor | Estado | Uso |
|---|---|---|---|
| `--freyja-bg` | `#090b12` | existe | Fondo de la aplicación |
| `--freyja-bg-glow` | `#10131d` | existe | Degradado de marca (solo autenticación / emblema) |
| `--freyja-card-bg` | `#12141e` | existe | Tarjetas, paneles, tablas |
| `--freyja-input-bg` | `#171a26` | existe | Campos de entrada |
| `--freyja-input-bg-focus` | `#1c2436` | existe | Campo con foco |
| `--freyja-surface-raised` | `#1c2030` | nuevo | Modales, menús, *popovers* (elevación por color, §10) |
| `--freyja-border` | `rgba(201, 162, 74, 0.28)` | existe | Borde de marca (tarjetas destacadas, inputs) |
| `--freyja-border-strong` | `#c9a24a` | existe | Borde activo / foco de input |
| `--freyja-border-subtle` | `rgba(241, 234, 217, 0.08)` | nuevo | Separadores neutros de tablas y listas densas, donde el borde dorado resultaría ruidoso |

### 6.2 Texto y acento

| Token | Valor | Estado | Contraste | Uso |
|---|---|---|---|---|
| `--freyja-text-cream` | `#f1ead9` | existe | 15.30:1 | Texto principal |
| `--freyja-text-muted` | `#9c9578` | existe | 6.10:1 | Texto secundario, etiquetas |
| `--freyja-text-disabled` | `#6f6a58` | nuevo | 3.39:1 | Solo texto deshabilitado (WCAG 1.4.3 lo exime; ver §17) |
| `--freyja-gold` | `#c9a24a` | existe | 7.65:1 | Etiquetas de marca, acentos |
| `--freyja-gold-bright` | `#e0bf7c` | existe | 10.41:1 | Acción principal, enlaces, anillo de foco |

### 6.3 Estados semánticos

| Token | Valor | Estado | Contraste | Rol |
|---|---|---|---|---|
| `--freyja-status-success` | `#8fd2ab` (= `--freyja-success`) | existe | 10.46:1 | Éxito |
| `--freyja-status-info` | `#7fb3e6` | nuevo | 8.29:1 | Información |
| `--freyja-status-warning` | `#f29d52` | nuevo | 8.49:1 | Advertencia |
| `--freyja-status-error` | `#e26a8a` (= `--freyja-error`) | existe | 5.82:1 | Error |
| `--freyja-status-blocked` | `#9aa0b4` | nuevo | 7.04:1 | Bloqueado / no disponible |
| `--freyja-env-demo` | `#b3a6f5` | nuevo | 8.47:1 | Entorno DEMO |
| `--freyja-env-real` | `#f0875f` | nuevo | 7.28:1 | Entorno REAL (texto oscuro `#090b12` sobre este fondo: 7.80:1) |

Todos los colores de texto y estado superan 4.5:1 (AA para texto normal)
sobre `--freyja-bg`, `--freyja-card-bg`, `--freyja-input-bg` y
`--freyja-surface-raised`, salvo `--freyja-text-disabled` (≈3:1,
deliberado y exento).

**Riesgo conocido:** `--freyja-status-warning` y `--freyja-gold` tienen
luminancia casi idéntica (relación 1.11:1) y tonos cercanos. Por eso
una advertencia **siempre** lleva icono de advertencia y texto, y el oro
nunca se usa para comunicar un estado. Ver §19.

### 6.4 Mercado y riesgo

| Token | Valor | Uso |
|---|---|---|
| `--freyja-market-up` | `#8fd2ab` | Variación positiva — siempre con `▲` y signo `+` |
| `--freyja-market-down` | `#e26a8a` | Variación negativa — siempre con `▼` y signo `−` |
| `--freyja-risk-low` / `-medium` / `-high` / `-critical` | reutilizan `status-info` / `status-warning` / `status-error` / `status-error` + borde doble | Siempre con etiqueta textual del nivel (§16) |

`market-up`/`market-down` comparten valor con éxito/error pero son tokens
distintos: una subida de precio no es un "éxito" ni una bajada un
"error". Mantenerlos separados permite cambiarlos (p. ej. para
daltonismo) sin afectar a los estados de sistema.

## 7. Preparación conceptual del tema claro

No se implementa ni se fijan valores ahora. Reglas para que sea posible
sin reescribir componentes:

- El tema claro se activará redefiniendo **solo los valores** de los
  tokens bajo un selector de tema (p. ej. `:root[data-theme='light']`),
  nunca con estilos alternativos por componente.
- Como los componentes solo consumen tokens (§4), cambiar de tema no debe
  requerir tocar ningún componente.
- Los tokens semánticos se nombran por rol, no por color: no se crearán
  tokens como `--freyja-dark-panel`.
- Los tokens existentes con nombre ligado al color (`--freyja-text-cream`,
  `--freyja-gold`) son un obstáculo menor para el tema claro (en claro, el
  texto principal no será crema); se resolvería con alias semánticos
  (§19).
- El tema claro deberá volver a medir todos los contrastes de §6; no se
  hereda ninguno.
- El placeholder `HomePage` (fondo blanco) **no** es un tema claro: es un
  estilo sin tokens pendiente de sustituir (§18).

## 8. Tipografía

Sin webfonts: se mantiene la decisión ya documentada en `styles.scss` de
no añadir una dependencia de red externa sin necesidad demostrada.

| Token | Valor | Uso |
|---|---|---|
| `--freyja-font-serif` | pila serif existente (`'Iowan Old Style', 'Palatino Linotype', Palatino, Georgia, …`) | Marca, títulos de pantalla y sección |
| `--freyja-font-sans` | `system-ui, -apple-system, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif` | Texto de interfaz, tablas, formularios fuera de autenticación |
| `--freyja-font-mono` | `ui-monospace, 'Cascadia Mono', 'Segoe UI Mono', Menlo, Consolas, monospace` | Símbolos, identificadores, código |

Cifras: toda celda o valor numérico usa `font-variant-numeric:
tabular-nums` para alinear decimales. Esta es una decisión nueva (la
autenticación usa serif para todo) y queda para validación (§19).

Escala (base 16px, en `rem`):

| Token | Tamaño | Uso |
|---|---|---|
| `--freyja-text-size-xs` | 0.75rem | Etiquetas en mayúsculas, metadatos, timestamps |
| `--freyja-text-size-sm` | 0.875rem | Texto de tabla, texto secundario |
| `--freyja-text-size-md` | 1rem | Texto base |
| `--freyja-text-size-lg` | 1.25rem | Títulos de tarjeta |
| `--freyja-text-size-xl` | 1.5rem | Títulos de sección |
| `--freyja-text-size-2xl` | 2rem | Título de pantalla |

Pesos: 400 (normal) y 600 (énfasis/títulos). Interlineado: 1.5 para texto,
1.25 para títulos. Las etiquetas en mayúsculas mantienen el
`letter-spacing` de la marca (≈0.12em) y nunca se usan para textos largos.

## 9. Escala de espaciado

Base de 4px (0.25rem). Solo estos valores:

| Token | Valor |
|---|---|
| `--freyja-space-1` | 0.25rem (4px) |
| `--freyja-space-2` | 0.5rem (8px) |
| `--freyja-space-3` | 0.75rem (12px) |
| `--freyja-space-4` | 1rem (16px) |
| `--freyja-space-5` | 1.5rem (24px) |
| `--freyja-space-6` | 2rem (32px) |
| `--freyja-space-7` | 2.5rem (40px) |
| `--freyja-space-8` | 3.5rem (56px) |

Los valores ya usados en autenticación (0.4rem, 0.9rem, 1.75rem…) no
encajan exactamente en la escala; se ajustarán al migrar esos estilos,
no ahora (§18).

## 10. Radios y elevación

| Token | Valor | Uso |
|---|---|---|
| `--freyja-radius-sm` | 0.15rem | Inputs, botones, badges (valor ya usado en autenticación) |
| `--freyja-radius-md` | 0.25rem | Tarjetas, modales, alertas (valor ya usado en la tarjeta de autenticación) |
| `--freyja-radius-full` | 999px | Solo indicadores circulares (p. ej. punto de estado) |

Elevación: en tema oscuro la profundidad se expresa con **superficies más
claras + borde**, no con sombras marcadas:

| Nivel | Superficie | Borde | Uso |
|---|---|---|---|
| 0 | `--freyja-bg` | — | Fondo |
| 1 | `--freyja-card-bg` | `--freyja-border-subtle` o `--freyja-border` | Tarjetas, tablas |
| 2 | `--freyja-surface-raised` | `--freyja-border` + sombra suave `0 8px 24px rgba(0,0,0,0.5)` | Modales, menús |

El resplandor dorado (`drop-shadow` del emblema) queda reservado a la
marca; no se usa en componentes de datos.

## 11. Movimiento y transición

| Token | Valor | Uso |
|---|---|---|
| `--freyja-motion-fast` | 150ms ease | Hover, foco, cambios de color (valor ya usado en autenticación) |
| `--freyja-motion-base` | 200ms ease-out | Apertura/cierre de modales, tabs, menús |

Reglas:

- Solo se animan color, opacidad y transformaciones pequeñas; nunca el
  layout de tablas de datos.
- **No se animan cifras** (contadores, parpadeos de precio) salvo que el
  dato sea realmente en vivo y lleve timestamp; una animación no puede
  sugerir actividad que no existe.
- `prefers-reduced-motion: reduce` desactiva transiciones y animaciones en
  **toda** la aplicación (hoy solo en `.auth-page`). Los indicadores de
  carga pasan a un estado estático con texto.

## 12. Semántica de estados

| Estado | Token | Canal no cromático obligatorio | Texto |
|---|---|---|---|
| Éxito | `--freyja-status-success` | Icono ✓ | Mensaje explícito |
| Información | `--freyja-status-info` | Icono ⓘ | Mensaje explícito |
| Advertencia | `--freyja-status-warning` | Icono ⚠ | Mensaje explícito (obligatorio: el color se confunde con el oro, §6.3) |
| Error | `--freyja-status-error` | Icono ✕ o ⚠ (el prefijo `⚠` ya usado en `.field-error`) | Mensaje explícito con causa y acción posible |
| Bloqueado | `--freyja-status-blocked` | Icono de candado | "Bloqueado" + motivo cuando exista (p. ej. `suspension_reasons`) |
| DEMO | `--freyja-env-demo` | Badge con borde (contorno) | Texto `DEMO` siempre visible |
| REAL | `--freyja-env-real` | Badge relleno (sólido) + candado mientras esté bloqueado | Texto `REAL` siempre visible; hoy siempre `REAL · Bloqueado` |

Los iconos citados son orientativos. Hoy no hay librería de iconos; ver
§19.

## 13. DEMO y REAL

Reglas vinculantes, coherentes con `UX-IA-001` §8:

- **Siempre etiquetados con texto.** Ningún dato ligado a un
  `ExecutionContext` se muestra sin su badge `DEMO` o `REAL`.
- **Diferenciados por forma, no solo por color.** DEMO = badge con
  contorno violeta. REAL = badge sólido coral con texto oscuro. Así se
  distinguen también en escala de grises o con daltonismo.
- **Ninguno reutiliza un color de estado de sistema:** DEMO no se parece a
  "éxito" ni a "información"; REAL no se parece a "error". Un entorno no
  es un resultado.
- **REAL está bloqueado y se ve bloqueado.** Mientras el backend lo
  mantenga *fail-closed*, todo elemento REAL se muestra como
  `REAL · Bloqueado`, con candado y, si existe, el motivo de
  `suspension_reasons`. El concepto REAL no se oculta, pero ningún control
  REAL aparece como disponible: no hay botón REAL habilitado en ningún
  componente de este sistema.
- **El estado de REAL lo decide el backend.** Los componentes solo
  reflejan `activation_status` y el resto de estados de
  `ExecutionContextOut`; nunca calculan disponibilidad en el cliente.
- Los estados de `ActivationStatus` (`NOT_CONFIGURED`, `CONFIGURED`,
  `ENABLED`, `SUSPENDED`) se muestran con su valor literal, sin colapsarse
  en "disponible/no disponible" (misma regla que ya aplica
  `catalog.models.ts` a `CapabilityStatus`).

## 14. Componentes base

Solo se definen reglas de apariencia y comportamiento. No se implementa
ninguno en esta tarea. Todos viven en `frontend/src/app/shared/`.

### 14.1 Botones

- **Variantes:** `primary` (contorno y texto `--freyja-gold-bright`: el
  estilo ya usado por el *submit* de autenticación), `secondary` (contorno
  `--freyja-border`, texto crema), `ghost` (sin borde, texto
  `--freyja-text-muted`; p. ej. mostrar/ocultar contraseña),
  `destructive` (contorno y texto `--freyja-status-error`, solo para
  acciones irreversibles y siempre con confirmación).
- Una sola acción `primary` por contexto visible.
- Tamaño mínimo del área interactiva: 44×44px en táctil (24×24px como
  mínimo absoluto WCAG 2.2).
- `loading`: conserva el ancho, muestra indicador y texto
  ("Guardando…"), queda deshabilitado y con `aria-busy="true"`.

### 14.2 Inputs

- Base: los inputs de `.auth-page` (fondo `--freyja-input-bg`, borde
  `--freyja-border`, foco `--freyja-input-bg-focus` + anillo dorado).
- Etiqueta visible siempre (nunca solo *placeholder*); ayuda y error
  debajo, enlazados con `aria-describedby`.
- Error: borde `--freyja-status-error` + mensaje con prefijo `⚠` +
  `aria-invalid="true"` (patrón ya implementado).
- Campos numéricos: alineados a la derecha, `tabular-nums`, unidad o
  divisa visible; el valor nunca se redondea en la interfaz de forma que
  oculte precisión que venga del contrato.

### 14.3 Tablas

- Superficie `--freyja-card-bg`, separadores `--freyja-border-subtle`,
  cabecera en `--freyja-text-size-xs` mayúsculas `--freyja-text-muted`.
- Texto a la izquierda; cifras a la derecha con `tabular-nums`; símbolos
  en `--freyja-font-mono`.
- Todo timestamp muestra su zona horaria explícitamente (nunca una hora
  "desnuda"). La zona por defecto de visualización es decisión pendiente
  (§19).
- Estados propios: cargando (filas *skeleton*), vacío (mensaje en el
  cuerpo de la tabla), error (mensaje + reintentar), parcial (columna o
  fila sin dato marcada `—` con texto accesible "sin dato", nunca `0`).
- Cabeceras reales (`<th scope="col">`); si hay ordenación, se indica con
  icono y `aria-sort`.

### 14.4 Tarjetas

- Superficie `--freyja-card-bg`, `--freyja-radius-md`, borde
  `--freyja-border-subtle` por defecto.
- Las esquinas doradas de `auth-shell` quedan como recurso de marca
  (autenticación, estados vacíos destacados), no como decoración de cada
  tarjeta de datos.
- Si una tarjeta muestra una métrica: título, valor, **fuente** y
  **timestamp** visibles (criterio ya fijado para el Dashboard; aplica a
  cualquier tarjeta de métrica).

### 14.5 Badges

- Texto corto en mayúsculas `--freyja-text-size-xs`, `--freyja-radius-sm`.
- Variantes: estados de §12 y entornos de §13. Contorno para estados
  informativos y DEMO; relleno solo para REAL.
- Nunca un badge solo con color o solo con icono: siempre texto.

### 14.6 Alertas

- Variantes: `success`, `info`, `warning`, `error`, `blocked`.
- Anatomía: icono + título opcional + mensaje + acción opcional.
- Fondo translúcido del color de estado (≈8%, como el `.notice` actual) y
  borde del color de estado; el texto sigue en `--freyja-text-cream` para
  mantener el contraste.
- `role="alert"` solo para errores que requieren atención inmediata;
  `role="status"` para el resto.

### 14.7 Modales

- Superficie nivel 2 (§10), fondo de página oscurecido.
- Foco atrapado dentro del modal; `Escape` cierra (salvo confirmaciones
  destructivas en curso); al cerrar, el foco vuelve al elemento que lo
  abrió.
- `role="dialog"`, `aria-modal="true"`, título enlazado con
  `aria-labelledby`.
- Las acciones destructivas requieren confirmación explícita en el modal;
  ningún modal ofrece ejecución REAL.

### 14.8 Tabs

- Tab activo: texto crema + indicador inferior dorado de 2px (no solo
  cambio de color).
- Navegación con flechas izquierda/derecha; `role="tablist"`, `tab`,
  `tabpanel` con `aria-selected`.

### 14.9 Elementos de navegación

Solo el elemento, no el layout del shell (que es `FRONTEND-SHELL-001`):

- **Ítem de navegación:** icono + etiqueta de texto (la etiqueta no se
  oculta en escritorio). Activo: texto `--freyja-gold-bright`, indicador
  lateral dorado y `aria-current="page"`.
- **Indicador de entorno en cabecera:** badge DEMO/REAL de §13, visible
  de forma permanente cuando la sección muestra datos de ejecución
  (`UX-IA-001` §5).
- **Enlace de "saltar al contenido"** como primer elemento enfocable.

### 14.10 Indicadores de carga

- *Skeleton* con bloques `--freyja-border-subtle` para contenido con forma
  conocida (tablas, tarjetas); indicador circular solo para acciones
  puntuales (botón `loading`).
- Nunca muestran cifras provisionales. `aria-busy="true"` en el contenedor
  y texto accesible "Cargando…".
- Con `prefers-reduced-motion`, el *skeleton* es estático.

### 14.11 Estado vacío

- Icono neutro + título + explicación de **por qué** está vacío + acción
  si existe (p. ej. "Aún no hay backtests ejecutados").
- Distinto visualmente del error: sin color de estado, tono
  `--freyja-text-muted`.
- Si la pantalla es conceptual (sin contrato, `UX-IA-001` §9), lo dice
  explícitamente: "Esta sección aún no está disponible". Nunca datos de
  ejemplo.

### 14.12 Estado de error

- Alerta `error` dentro del área afectada, no a pantalla completa, salvo
  que falle la carga de la pantalla entera.
- Mensaje comprensible + acción de reintento cuando tenga sentido. No se
  muestran trazas, códigos internos ni detalles técnicos del backend.

### 14.13 Estado desconectado

- Distingue **sesión expirada** (redirección a `/login` con el aviso ya
  existente `expired=1`) de **API inalcanzable** (5xx/timeout).
- API inalcanzable: banner persistente `blocked`/`warning` en la parte
  superior con texto "Sin conexión con Freyja" y la hora de la última
  actualización válida; los datos visibles se marcan como potencialmente
  desactualizados, no se borran ni se presentan como actuales.

## 15. Matriz de variantes interactivas

| Variante | Regla general | Botón | Input | Tab / ítem de navegación |
|---|---|---|---|---|
| default | Tokens base | Contorno según variante | Fondo `input-bg`, borde `border` | Texto `text-muted` |
| hover | Solo cambio de fondo/color, sin mover layout | Fondo del color de la variante al 12% | Borde `border-strong` | Texto crema |
| focus | Anillo `2px solid --freyja-gold-bright`, `offset 2px`, **siempre visible** con teclado (`:focus-visible`) | Anillo | Anillo + fondo `input-bg-focus` | Anillo |
| active | Fondo del color de la variante al 20% | Presionado | — | Indicador dorado + `aria-current`/`aria-selected` |
| disabled | Opacidad 0.5 + `cursor: not-allowed` + atributo `disabled` real | Sí | Sí, texto `text-disabled` | Ítem no disponible: con candado y texto, no oculto |
| loading | Conserva tamaño, `aria-busy`, texto de progreso | Indicador + texto | — | — |
| error | Color de error + icono + texto | Solo si la acción falló: alerta asociada | Borde error + mensaje `⚠` + `aria-invalid` | — |

## 16. Gráficos y riesgo sin depender del color

No se elige librería de gráficos (requiere decisión arquitectónica). Reglas
para cualquier implementación futura:

- **Subida/bajada:** siempre flecha (`▲`/`▼`) y signo (`+`/`−`) además del
  color.
- **Series múltiples:** se distinguen por color **y** por estilo de línea
  (continua, discontinua, punteada) o marcador; leyenda con texto siempre
  visible.
- **Niveles de riesgo:** etiqueta textual obligatoria (`Bajo`, `Medio`,
  `Alto`, `Crítico`) + forma o intensidad (p. ej. barras de nivel 1–4); el
  nivel crítico añade borde doble. El color solo refuerza.
- **Zonas de riesgo en gráficos:** tramas o patrones (rayado) además del
  tono.
- **Ejes y fuentes:** todo gráfico indica unidad, zona horaria, fuente de
  datos y timestamp de la última actualización.
- **Honestidad:** ningún gráfico muestra datos de ejemplo, series
  simuladas presentadas como reales ni proyecciones sin etiquetar como
  tales. Un gráfico sin datos es un estado vacío (§14.11).
- **Alternativa accesible:** todo gráfico ofrece un resumen textual o una
  tabla equivalente.

## 17. Accesibilidad

Objetivo: WCAG 2.2 nivel AA.

- **Contraste:** texto normal ≥ 4.5:1; texto grande (≥ 1.5rem o ≥ 1.2rem
  en negrita) ≥ 3:1; bordes de componentes, iconos con significado y
  anillo de foco ≥ 3:1 contra la superficie adyacente. Los valores de §6
  cumplen en tema oscuro. El texto deshabilitado está exento, pero un
  elemento deshabilitado nunca es el único portador de información
  importante.
- **Foco visible:** anillo dorado de §15 en todo elemento interactivo. Se
  prohíbe `outline: none` sin sustituto equivalente.
- **Teclado:** todo es operable con teclado en orden lógico; sin trampas
  de foco (salvo el atrapamiento intencionado de los modales, con salida
  por `Escape`); enlace "saltar al contenido".
- **No solo color:** regla del §3.4, aplicada en §12, §13 y §16.
- **Nombres accesibles:** todo control tiene etiqueta visible o
  `aria-label`; los botones de solo icono llevan `aria-label`; los badges
  DEMO/REAL y los estados se leen en texto por lectores de pantalla.
- **Contenido dinámico:** `role="status"`/`aria-live="polite"` para
  cambios no urgentes; `role="alert"` solo para errores urgentes.
- **Idioma:** `lang="es"` (ya presente en `index.html`).
- **Movimiento reducido:** §11.

## 18. Conflictos detectados con estilos existentes

Se reportan; **no** se corrigen en esta tarea.

1. **`HomePage` usa colores claros hardcodeados** (`#ffffff`, `#1a1a1a`) y
   `system-ui`, sin ningún token. Contradice el tema oscuro y la fuente
   única de verdad. Es el placeholder que sustituirá `FRONTEND-SHELL-001`.
2. **Los estilos de formulario viven solo bajo `.auth-page`** en
   `styles.scss`. Son equivalentes a los inputs, botones y alertas de §14.
   Cuando se implementen los componentes genéricos habrá que migrarlos y
   retirar la versión de `.auth-page` en la misma tarea, para no tener dos
   implementaciones.
3. **Espaciados fuera de escala en autenticación** (0.4rem, 0.9rem,
   1.75rem…) respecto a la escala de §9.
4. **`prefers-reduced-motion` solo cubre `.auth-page`**; §11 exige que
   cubra toda la aplicación.
5. **Nombres de tokens existentes ligados al color** (`text-cream`,
   `gold`), no al rol; dificultan el tema claro (§7).

## 19. Decisiones pendientes

No se resuelven aquí; se exponen para el Arquitecto:

1. **Tonos concretos de DEMO (violeta `#b3a6f5`) y REAL (coral
   `#f0875f`).** Son una propuesta medida y diferenciada por forma, pero
   la elección de color de los entornos es una decisión de producto.
2. **Advertencia vs. oro de marca.** Luminancia casi idéntica (1.11:1).
   Mitigado con icono + texto obligatorios. Alternativa: un tono de
   advertencia más rojizo, que a su vez se acercaría a REAL y a error.
3. **Tipografía sans + cifras tabulares para la interfaz de datos**, en
   vez de la serif de autenticación. Cambia la sensación visual fuera de
   la marca.
4. **Librería de iconos.** Hoy no existe ninguna; los estados de §12
   requieren iconos. Opciones: SVG inline propios en `shared/` (sin
   dependencia, mismo patrón que `rune-mark`) o una librería (requiere
   decisión arquitectónica). Recomendación: SVG propios.
5. **Librería de gráficos.** Sin elegir; §16 define reglas agnósticas.
6. **Zona horaria de visualización por defecto** (UTC frente a la hora
   local de Jessica). La regla fija que siempre se muestre la zona; falta
   decidir cuál por defecto.
7. **Alias semánticos para los tokens existentes** (p. ej.
   `--freyja-text-primary` → `--freyja-text-cream`) o renombrado real.
   Cualquiera de los dos es un cambio de código fuera de esta tarea.
8. **Qué tarea implementa los tokens nuevos y migra `.auth-page`** a los
   componentes genéricos: ¿`FRONTEND-SHELL-001` o una tarea de
   implementación del sistema visual dedicada?

## 20. Fuera de alcance

- Diseño del Dashboard (`UX-DASHBOARD-001`) y de cualquier pantalla
  concreta.
- Implementación del shell o la navegación (`FRONTEND-SHELL-001`).
- Cualquier cambio en `styles.scss` o en componentes existentes: los
  tokens nuevos de este documento **no** están implementados.
- Implementación del tema claro.
- Elección o incorporación de librerías UI, de iconos o de gráficos.
- Conexión con APIs y datos de trading de cualquier tipo.
- Cambios al sitemap o a las rutas aprobadas en `UX-IA-001`.
- Cualquier habilitación de REAL.
