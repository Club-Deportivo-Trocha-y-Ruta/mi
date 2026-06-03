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
| `frontend/e2e/monthly-technical-report-parent.spec.ts` | Vista padre (privacidad): ve métricas + nota "solo para el equipo técnico"; NO ve editores, NO botón Aprobar, NO descarga PDF, NO tabla de competición. |

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
- **Contrato de privacidad del padre.** El fixture del padre entrega
  `narrative_blocks=null` y `competition_results=null`, replicando lo que el
  backend filtra. La UI del padre se valida en consecuencia.

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

### Validación sin navegador (lo que SÍ corre offline)

Aun sin poder lanzar el navegador, se puede verificar que los specs compilan y
colectan (TypeScript + parsing de Playwright). Esto **no** requiere Chromium:

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
| ITR-008 | parent | Privacidad: ve métricas + nota; sin editores, sin Aprobar, sin PDF. |

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
- [ ] Ir al detalle del reporte del mes.
- [ ] Confirmar que el padre **ve** la tabla de métricas (solo de sus atletas).
- [ ] Confirmar la nota "El informe técnico completo está disponible solo para
      el equipo técnico del club".
- [ ] Confirmar que el padre **NO ve**: editores de bloque, botón Aprobar, botón
      de descarga de PDF, tabla de competición, ni datos de atletas ajenos.
- [ ] Confirmar en la respuesta de red que `narrative_blocks` y
      `competition_results` llegan `null` para el padre.

---

## 4. Nota honesta sobre el estado de validación

Los specs `monthly-technical-report-coach.spec.ts` y
`monthly-technical-report-parent.spec.ts` se escribieron siguiendo el patrón de
mock existente (`newsletters-coach.spec.ts`) y se **validaron con
`playwright test --list`** (compilan y colectan los 8 tests sin errores de
TypeScript). Adicionalmente, `npx tsc --noEmit` permanece limpio.

La **ejecución con navegador** (lanzar Chromium contra Vite dev) **queda
pendiente** de un entorno con acceso a red, ya que el contenedor de desarrollo
actual no puede descargar el binario de Chromium (`npx playwright install
chromium`) ni levantar el backend. En cuanto se disponga de red, basta correr
`npm run test:e2e` para ejecutarlos de verdad.
