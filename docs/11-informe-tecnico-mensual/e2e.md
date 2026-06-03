# Pruebas E2E — Módulo Informe Técnico Mensual

Este documento describe las pruebas end-to-end (E2E) del módulo **Informe Técnico
Mensual** (refactor del reporte mensual del club), cómo ejecutarlas y cuándo usar
cada modalidad.

Hay dos modalidades de E2E para este módulo:

1. **E2E mockeados (Playwright + `page.route`)** — sin backend, sin red, rápidos
   y deterministas. Son los que viven en `frontend/e2e/monthly-technical-report-*.spec.ts`.
2. **E2E full-stack (manual, contra backend real)** — Docker Compose + seed +
   `AI_PROVIDER=fake`. Checklist al final de este documento.

---

## 1. E2E mockeados (Playwright)

### Archivos

| Archivo | Cobertura |
|---|---|
| `frontend/e2e/monthly-technical-report-coach.spec.ts` | Vista coach: lista, detalle (7 bloques, métricas, competición), editar+guardar bloque (PATCH), regenerar bloque (POST), aprobar (PATCH status), descargar PDF (GET blob), project profile (PUT). |
| `frontend/e2e/monthly-technical-report-parent.spec.ts` | Privacidad: el padre **no** accede a la ruta del informe (`[coach, admin]`); por URL directa es redirigido a `/my-athletes` y no ve métricas, editores, Aprobar, PDF ni competición. |

### Cómo funcionan

- **Sin backend real.** Todos los endpoints `**/api/...` se interceptan con
  `page.route(...)` y devuelven fixtures deterministas. Un objeto `state` mutable
  cuenta llamadas (`patchCalls`, `regenerateCalls`, `pdfCalls`, `putCalls`) y
  muta el recurso (p.ej. al aprobar, `status` pasa a `"approved"`; al regenerar,
  el `ai_draft` cambia).
- **Sesión inyectada.** `setupAuth(page)` escribe la sesión Zustand en
  `sessionStorage` bajo la clave `"auth-session"` (formato
  `{state:{accessToken,refreshToken,user,isAuthenticated,isLoading},version:0}`),
  evitando el flujo de login por UI. El usuario coach tiene `role:"coach"` y
  `club_ids:[1]`; el padre `role:"parent"` y `club_ids:[1]`.
- **Fixtures sin datos reales de menores.** Nombres ficticios tipo
  "Valentina Garcia" / "Mateo Lopez" / "Madre Ficticia". Ningún dato real de
  atletas TyR.
- **Contrato de privacidad del padre.** El Informe Técnico Mensual es un
  documento **interno** del equipo técnico (coach/admin). La ruta
  `/training/reports/:year/:month` está protegida con `allowedRoles
  [coach, admin]` y el link del sidebar tampoco se muestra a padres, así que un
  padre que entre por URL directa es redirigido a `/my-athletes` (ver
  `ProtectedRoute`). El E2E del padre valida esa expulsión + la ausencia total de
  UI del informe. El mock del padre se conserva como red defensiva por si el SPA
  prefetchea antes de resolver el guard.

  > Nota de código muerto: `ReportDetailPage` conserva un `ParentReadOnlyView`
  > (con su unit test que monta el componente directamente). Hoy **no es
  > alcanzable** por routing/nav para padres. Decisión del coach (2026-06-03):
  > el informe queda interno; el padre se bloquea. El fallback y su unit test son
  > candidatos a limpieza aparte.

### Requisitos para ejecutar (entorno con red)

El navegador (Chromium) debe estar instalado. En este repositorio el binario
**no** está versionado y el contenedor de CI/sandbox sin red **no** puede
descargarlo. Para ejecutarlos en un entorno con red:

```bash
cd frontend
npx playwright install chromium    # descarga el shell de Chromium (requiere red)
npm run test:e2e                    # corre toda la carpeta e2e/
```

El `webServer` de `playwright.config.ts` arranca automáticamente
`npm run dev -- --port 5173` (Vite dev en `http://localhost:5173`, que es el
`baseURL`). **No** hace falta levantar Vite a mano: Playwright lo gestiona y
reusa una instancia existente fuera de CI (`reuseExistingServer`).

Para correr solo este módulo:

```bash
cd frontend
npx playwright test e2e/monthly-technical-report-coach.spec.ts e2e/monthly-technical-report-parent.spec.ts
```

Para apuntar a un Chromium del sistema sin descargar (entorno restringido):

```bash
PLAYWRIGHT_CHROMIUM_PATH=/ruta/a/chromium npm run test:e2e
```

(`playwright.config.ts` usa `executablePath` cuando esa variable está definida.)

### Validación rápida sin navegador (smoke offline)

Como chequeo veloz —o en un entorno sin Chromium— se puede verificar que los
specs compilan y colectan (TypeScript + parsing de Playwright) sin lanzar el
navegador:

```bash
cd frontend
npx playwright test --list e2e/monthly-technical-report-*.spec.ts
```

Salida esperada (8 tests, 2 archivos):

```
Listing tests:
  [chromium] › monthly-technical-report-coach.spec.ts › ... › ITR-001 ...
  [chromium] › monthly-technical-report-coach.spec.ts › ... › ITR-002 ...
  [chromium] › monthly-technical-report-coach.spec.ts › ... › ITR-003 ...
  [chromium] › monthly-technical-report-coach.spec.ts › ... › ITR-004 ...
  [chromium] › monthly-technical-report-coach.spec.ts › ... › ITR-005 ...
  [chromium] › monthly-technical-report-coach.spec.ts › ... › ITR-006 ...
  [chromium] › monthly-technical-report-coach.spec.ts › ... › ITR-007 ...
  [chromium] › monthly-technical-report-parent.spec.ts › ... › ITR-008 ...
Total: 8 tests in 2 files
```

### Mapa de escenarios

| ID | Rol | Escenario |
|---|---|---|
| ITR-001 | coach | Lista muestra badge de estado + enlace "Datos del proyecto". |
| ITR-002 | coach | Detalle: 7 editores en orden, tabla de métricas, tabla de competición. |
| ITR-003 | coach | Editar `final_text` + Guardar → `PATCH .../blocks` (cuenta + body). |
| ITR-004 | coach | Regenerar bloque → `POST .../regenerate` (cuenta + `ai_draft` cambia). |
| ITR-005 | coach | Aprobar → `PATCH status=approved`; badge "Aprobado"; editores deshabilitados. |
| ITR-006 | coach | Descargar PDF → `GET .../pdf` blob `application/pdf`; sin romper UI. |
| ITR-007 | coach | Project profile: llenar, agregar/quitar objetivo, Guardar → `PUT`. |
| ITR-008 | parent | Privacidad: por URL directa es redirigido a `/my-athletes`; sin métricas, sin editores, sin Aprobar, sin PDF, sin competición. |

---

## 2. Diferencia con los E2E full-stack del repo y cuándo usar cada uno

| | E2E mockeados (`page.route`) | E2E full-stack (Docker + seed) |
|---|---|---|
| **Backend** | Ninguno. Endpoints interceptados. | FastAPI real (`docker compose up`). |
| **DB** | Ninguna. | MySQL con datos sembrados (seed). |
| **IA** | Respuestas fijas en el fixture. | `AI_PROVIDER=fake` (o real bajo control). |
| **Red** | No requiere. | Requiere stack levantado. |
| **Velocidad / flake** | Rápidos y deterministas. | Más lentos; sensibles a estado de DB. |
| **Qué validan** | Wiring rutas + UI + contrato de API (forma de request/response) + invariantes de privacidad en la UI. | El sistema real de punta a punta: cálculo de métricas, generación IA con guardrails, persistencia, RBAC en el backend, PDF real. |

**Cuándo usar cuál:**

- **Mockeados** — en cada PR / CI del frontend. Verifican que la UI llama a los
  endpoints correctos con los payloads correctos y que renderiza/oculta lo que
  debe según rol. Son la primera línea de defensa contra regresiones de UI y
  contra fugas de privacidad en la vista del padre.
- **Full-stack manual** — antes de un deploy del módulo, o tras cambios en el
  backend (servicio de métricas, builder de bloques, generación IA, PDF). Validan
  que los datos reales fluyen correctamente y que el PDF generado coincide con el
  informe objetivo. Usar el checklist de la sección 3.

> Importante: los E2E mockeados **no** sustituyen a los tests unitarios (vitest)
> ni a los tests backend (pytest). Cobertura de contratos, RBAC negativo y
> guardrails de IA viven allí; el E2E mockeado valida el ensamblaje de UI.

---

## 3. Checklist de E2E MANUAL (full-stack contra backend real)

Objetivo: validar el módulo de punta a punta con datos sembrados de **un mes
cerrado** (todas las sesiones del período ya ejecutadas/registradas).

### Preparación del entorno

- [ ] Levantar el stack: `docker compose up` (aplica migraciones + seed).
- [ ] Confirmar `APP_ENV=development` para que corra el seed.
- [ ] Configurar `AI_PROVIDER=fake` (o `AI_ENABLED=false` para validar el camino
      sin IA) — **no** usar la API real de Gemini en pruebas manuales rutinarias.
- [ ] Verificar `AI_LOG_PROMPTS=false` y `NOTIFICATION_LOG_BODIES=false`
      (obligatorio: privacidad de menores).
- [ ] Login como coach (`entrenador@trochyruta.com` / `Coach2026!`).

### Sembrar datos de un mes cerrado (vía UI o seed)

- [ ] Capturar varias **sesiones** del mes con `session_kind` y `objectives`.
- [ ] Registrar **asistencia** por atleta (presente/tarde/justificado/ausente/lesionado).
- [ ] Registrar **rúbricas** (esfuerzo / actitud / técnica) en sesiones ejecutadas.
- [ ] Subir al menos una **foto consentida** a una sesión (`consent_ack`).
- [ ] Registrar el **resultado de una válida** del mes (Copa Valle) para tener
      `competition_results`.

### Datos del proyecto

- [ ] Ir a **/training/reports → "Datos del proyecto"**.
- [ ] Llenar nombre, entidad ejecutora, responsable, propósito, objetivo general,
      territorio.
- [ ] Agregar 2-3 **objetivos específicos**; quitar uno; reordenar mentalmente.
- [ ] Guardar → confirmar mensaje de éxito y que persiste tras recargar (PUT OK).

### Generar el informe

- [ ] En **/training/reports**, "Generar reporte" del mes cerrado (año/mes).
- [ ] Confirmar redirección al detalle `/training/reports/{year}/{month}`.
- [ ] Verificar **métricas**: sesiones ejecutadas/canceladas, asistencia por
      atleta, totales por estado, promedios de rúbrica, focos técnicos.
- [ ] Verificar que aparecen los **7 bloques narrativos** en orden:
      objetivo, desarrollo, resultados, conclusiones, apoyos_materiales,
      analisis_grupo, competencia.
- [ ] Verificar **tabla de competición** con el resultado de la válida.

### Editar / regenerar / aprobar bloques

- [ ] Editar el `final_text` de un bloque y **Guardar** → confirmar "Guardado".
- [ ] **Regenerar** un bloque con IA → confirmar que el `ai_draft` cambia y que
      el banner "Texto generado por IA — revísalo antes de aprobar" aparece.
- [ ] Confirmar guardrails de IA: sin nombres propios de menores en el texto,
      sin juicios individuales, dentro del límite de longitud.
- [ ] **Aprobar** el informe → badge pasa a "Aprobado"; los editores quedan
      deshabilitados (no se puede editar ni regenerar tras aprobar).

### PDF

- [ ] **Descargar PDF** desde el detalle → confirmar `Content-Type: application/pdf`.
- [ ] Abrir el PDF y **compararlo con el informe objetivo**: header del proyecto,
      métricas, bloques narrativos, antropometría (si aplica) solo en el PDF,
      resultados de competencia, footer Ley 1581.
- [ ] Confirmar que el nombre del archivo es `informe-tecnico-{year}-{MM}.pdf`.

### Privacidad — vista del padre

- [ ] Logout y login como padre (`padre@trochayruta.com` / `Parent2026!`).
- [ ] Confirmar que el sidebar del padre **no** muestra el acceso a Informes /
      `/training/reports`.
- [ ] Intentar entrar por URL directa a `/training/reports/{year}/{month}` →
      confirmar **redirección a `/my-athletes`** (el informe es interno del club).
- [ ] Confirmar que el padre **NO ve** nada del informe: métricas, editores de
      bloque, botón Aprobar, descarga de PDF ni tabla de competición.
- [ ] (Defensa en profundidad del backend) Si se consulta el endpoint del reporte
      como padre, confirmar que `narrative_blocks` y `competition_results` llegan
      `null` y que solo se exponen métricas de sus propios atletas.

---

## 4. Estado de validación

Los 8 specs **se ejecutan de verdad** con Chromium contra el Vite dev server
(`webServer` de `playwright.config.ts`, sin backend real): **8/8 en verde**
(~2.5s). `npx tsc --noEmit` permanece limpio.

La primera ejecución real (que la validación previa por solo `--list` no podía
detectar) reveló **2 fallos de selector/premisa**, ya corregidos:

- **ITR-001** — `getByText("Borrador").first()` tomaba la primera coincidencia
  del DOM, que es la card mobile (`ul md:hidden`), oculta en el viewport por
  defecto (1280px). Corregido con `.filter({ visible: true }).first()` para
  apuntar a la variante visible (tabla desktop).
- **ITR-008** — el spec asumía que el padre veía un `ParentReadOnlyView` con
  métricas en `/training/reports/:year/:month`. En realidad el app bloquea a los
  padres de esa ruta de forma consistente (guard `[coach, admin]` + link de nav
  oculto) y los redirige a `/my-athletes`. Reescrito para afirmar esa expulsión
  como invariante de privacidad (sin cambiar el app). Ver la nota de código
  muerto sobre `ParentReadOnlyView` en la sección 1.

Para reproducir:

```bash
cd frontend
npx playwright test e2e/monthly-technical-report-coach.spec.ts e2e/monthly-technical-report-parent.spec.ts
```
