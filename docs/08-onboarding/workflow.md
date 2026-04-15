# Workflow: Implementación Flujo de Onboarding

**Fecha:** 2026-04-15
**Basado en:** `docs/08-onboarding/research.md`, `docs/08-onboarding/design.md`
**Prerequisito:** Módulo de padres implementado (`docs/06-parents/workflow.md`)

---

## Resumen

17 pasos organizados en 5 fases. Cada paso indica el agente especializado responsable, archivos a crear/modificar, y dependencias. Los pasos sin dependencias entre sí pueden ejecutarse en paralelo.

---

## Fase A — Backend: Modelo de Datos y Migración

### Paso 1: Crear modelo `ParentalConsent`
**Agente:** `fastapi-architect`
**Archivos:**
- Crear: `backend/app/models/parental_consent.py`
- Modificar: `backend/app/models/__init__.py` (agregar import)

**Detalle:**
- Tabla `parental_consents` con campos: id, parent_user_id (FK users), athlete_id (FK athletes), consent_version, consented_at, consent_method, ip_address, data_collection, training_tracking, anthropometry, third_party_sharing, withdrawn_at
- Índices: `(parent_user_id, athlete_id)`, `athlete_id`
- Relationships: parent → User, athlete → Athlete

**Criterio de éxito:** Modelo importable, sin errores de sintaxis.
**Dependencias:** Ninguna
**Estimado:** Pequeño

---

### Paso 2: Generar migración Alembic
**Agente:** `fastapi-architect`
**Comando:**
```bash
cd backend && alembic revision --autogenerate -m "add_parental_consents_table"
```
**Verificación:**
```bash
cd backend && alembic upgrade head
```

**Criterio de éxito:** Migración aplica sin errores. Tabla `parental_consents` existe en DB.
**Dependencias:** Paso 1
**Estimado:** Pequeño

---

### Paso 3: Extender schemas Pydantic
**Agente:** `fastapi-architect`
**Archivos:**
- Modificar: `backend/app/schemas/parent_invite.py`

**Cambios:**
1. Agregar `ParentalConsentData` schema (accept_data_collection, accept_training_tracking, accept_anthropometry, accept_third_party, privacy_policy_version)
2. Agregar `consent: ParentalConsentData` y `relationship_type: str = "acudiente"` a `ParentRegisterRequest`
3. Agregar `role: str = "parent"` y `club_name: str = ""` a `ParentInviteTokenValidation`
4. Crear `ParentalConsentOut` schema para respuestas futuras

**Criterio de éxito:** Schemas validan correctamente. Tests de importación pasan.
**Dependencias:** Ninguna (puede ir paralelo con Paso 1)
**Estimado:** Pequeño

---

### Paso 4: Extender servicio `consume_invite()`
**Agente:** `fastapi-architect`
**Archivos:**
- Modificar: `backend/app/services/invitations.py`

**Cambios:**
1. Agregar parámetros: `relationship_type: str`, `consent: ParentalConsentData`, `ip_address: str | None`
2. Usar `relationship_type` para crear `ParentAthlete` (en vez de hardcoded "acudiente")
3. Crear `ParentalConsent` record con datos del consentimiento
4. Actualizar `athlete.parental_consent_obtained = True` y `athlete.parental_consent_date`
5. Mantener backward compatibility: parámetros nuevos con defaults

**Criterio de éxito:** `consume_invite()` crea User + ClubMember + ParentAthlete + ParentalConsent en transacción atómica.
**Dependencias:** Paso 1, Paso 3
**Estimado:** Mediano

---

### Paso 5: Actualizar endpoint `POST /api/auth/parent-register`
**Agente:** `fastapi-architect`
**Archivos:**
- Modificar: `backend/app/routers/auth.py`

**Cambios:**
1. Pasar `body.relationship_type`, `body.consent`, y `request.client.host` a `consume_invite()`
2. Agregar `Request` como dependency para obtener IP

**Criterio de éxito:** Endpoint acepta payload extendido y registra consentimiento.
**Dependencias:** Paso 4
**Estimado:** Pequeño

---

### Paso 6: Actualizar endpoint `GET /api/auth/invite/{token}`
**Agente:** `fastapi-architect`
**Archivos:**
- Modificar: `backend/app/routers/auth.py`

**Cambios:**
1. Incluir `role="parent"` en respuesta
2. Obtener `club_name` del atleta y agregarlo a respuesta

**Criterio de éxito:** Respuesta incluye role y club_name.
**Dependencias:** Paso 3
**Estimado:** Pequeño

---

## Fase B — Backend: Template Email

### Paso 7: Crear template email HTML
**Agente:** `fastapi-architect`
**Archivos:**
- Crear: `backend/templates/email/parent_invite.html`

**Detalle:**
- Template Jinja2 con inline CSS (compatibilidad email)
- Variables: `{{ athlete_first_name }}`, `{{ club_name }}`, `{{ invite_url }}`
- Diseño: header verde (#16a34a), contenido con beneficios, botón CTA, footer club
- Responsive (max-width: 600px)
- Autoescaping Jinja2 habilitado

**Criterio de éxito:** Template renderiza correctamente con variables de prueba. No hay XSS posible.
**Dependencias:** Ninguna (paralelo con Fase A)
**Estimado:** Pequeño

---

### Paso 8: Fix URL en generación de invitaciones
**Agente:** `fastapi-architect`
**Archivos:**
- Modificar: `backend/app/routers/parent_athletes.py` (línea ~264)

**Cambio:**
- Cambiar URL de invitación de `/registro-padre?token=` a `/onboarding?token=`
- O usar variable de configuración `ONBOARDING_URL` en `config.py`

**Criterio de éxito:** URL generada apunta a `/onboarding?token={token}`.
**Dependencias:** Ninguna (paralelo)
**Estimado:** Pequeño

---

## Fase C — Frontend: Infraestructura del Wizard

### Paso 9: Crear schemas Zod de onboarding
**Agente:** `react-ui-engineer`
**Archivos:**
- Crear: `frontend/src/schemas/onboarding.schema.ts`

**Detalle:**
- `accountSchema`: password + password_confirm con refinement
- `parentProfileSchema`: first_name, last_name, phone, relationship_type
- `consentSchema`: 3 obligatorios (literal true) + 1 opcional (boolean)
- `onboardingFormSchema`: combinación para type-safety
- Type export: `OnboardingFormData`

**Criterio de éxito:** Schemas compilan sin errores TypeScript. Validaciones correctas.
**Dependencias:** Ninguna (paralelo con backend)
**Estimado:** Pequeño

---

### Paso 10: Crear Zustand store de onboarding
**Agente:** `react-ui-engineer`
**Archivos:**
- Crear: `frontend/src/stores/onboarding-store.ts`

**Detalle:**
- State: currentStep, role, token, email, athleteName, clubName, formData
- Actions: setStep, setTokenData, updateFormData, reset
- Middleware: `persist` con key `"trocha-onboarding"` en localStorage

**Criterio de éxito:** Store persiste y recupera estado correctamente.
**Dependencias:** Ninguna (paralelo)
**Estimado:** Pequeño

---

### Paso 11: Crear hook `useOnboarding`
**Agente:** `react-ui-engineer`
**Archivos:**
- Crear: `frontend/src/hooks/onboarding/useOnboarding.ts`
- Crear: `frontend/src/hooks/onboarding/index.ts`

**Detalle:**
- `useValidateToken(token)` — TanStack Query wrapping `GET /api/auth/invite/{token}`
- `useCompleteOnboarding()` — Mutation wrapping `POST /api/auth/parent-register`
- Manejo de errores: 410 (expirado), 409 (email duplicado), 500 (server error)

**Criterio de éxito:** Hooks funcionan con TanStack Query. Loading/error states correctos.
**Dependencias:** Paso 9 (tipos), API client existente
**Estimado:** Pequeño

---

### Paso 12: Actualizar API client
**Agente:** `react-ui-engineer`
**Archivos:**
- Modificar: `frontend/src/api/parents.ts` (o crear `frontend/src/api/onboarding.ts`)

**Cambios:**
- Actualizar `registerParent()` para incluir `relationship_type` y `consent` en payload
- Actualizar tipo de respuesta de `validateInviteToken()` para incluir `role` y `club_name`

**Criterio de éxito:** API client alineado con schemas backend actualizados.
**Dependencias:** Paso 3 (schemas backend definidos)
**Estimado:** Pequeño

---

## Fase D — Frontend: Componentes del Wizard

### Paso 13: Crear componente `OnboardingStepper`
**Agente:** `react-ui-engineer`
**Archivos:**
- Crear: `frontend/src/components/onboarding/OnboardingStepper.tsx`
- Crear: `frontend/src/components/onboarding/onboarding-steps.ts` (config declarativa)

**Detalle:**
- Stepper visual custom con primitivas shadcn (Badge, Separator)
- Props: steps (StepConfig[]), currentStep (number)
- Muestra: ícono + label por paso, estado (completed/current/pending)
- Responsive: horizontal en desktop, vertical en mobile
- Config declarativa `ONBOARDING_STEPS` con roles, schemas, fields, components

**Criterio de éxito:** Stepper renderiza correctamente para 4 pasos (parent) y 4 pasos (coach futuro).
**Dependencias:** Paso 9
**Estimado:** Mediano

---

### Paso 14: Crear componentes de cada paso
**Agente:** `react-ui-engineer`
**Archivos:**
- Crear: `frontend/src/components/onboarding/steps/AccountStep.tsx`
- Crear: `frontend/src/components/onboarding/steps/ParentProfileStep.tsx`
- Crear: `frontend/src/components/onboarding/steps/ConsentStep.tsx`
- Crear: `frontend/src/components/onboarding/steps/ConfirmStep.tsx`

**Detalle por componente:**

**AccountStep:**
- Email (readonly, pre-rellenado desde token)
- Password con indicador de fortaleza
- Password confirm
- Usa shadcn Input, Label

**ParentProfileStep:**
- Nombre, Apellido (Input)
- Teléfono (Input, opcional)
- Parentesco (Select: padre/madre/acudiente)
- Usa shadcn Input, Label, Select

**ConsentStep:**
- Card con explicación de datos recolectados
- 3 Checkbox obligatorios con descripciones detalladas
- 1 Checkbox opcional (terceros)
- Link a política de privacidad
- Nombre del atleta contextualizado
- Usa shadcn Checkbox, Card, Alert

**ConfirmStep:**
- Resumen de todos los datos ingresados (readonly)
- Mensaje: "Serás vinculado como [parentesco] de [atleta] en [club]"
- Botón "Crear cuenta" (submit final)
- Usa shadcn Card, Badge, Button

**Criterio de éxito:** Cada componente renderiza y valida independientemente.
**Dependencias:** Paso 9, Paso 13
**Estimado:** Grande

---

### Paso 15: Crear `OnboardingWizard` container
**Agente:** `react-ui-engineer`
**Archivos:**
- Crear: `frontend/src/components/onboarding/OnboardingWizard.tsx`

**Detalle:**
- Props: `{ role, tokenData, onComplete }`
- Filtra `ONBOARDING_STEPS` por rol
- `FormProvider` wrapping (React Hook Form)
- `defaultValues` hidratados desde Zustand store
- `handleNext()`: `trigger(fields)` → `updateFormData()` → `setStep(+1)`
- `handleBack()`: `setStep(-1)`
- `handleSubmit()`: en último paso, llama `onComplete(formData)`
- Animación de transición entre pasos (opcional, CSS transition)

**Criterio de éxito:** Wizard navega correctamente, valida por paso, persiste estado.
**Dependencias:** Paso 10, Paso 13, Paso 14
**Estimado:** Mediano

---

### Paso 16: Crear `OnboardingPage` y actualizar rutas
**Agente:** `react-ui-engineer`
**Archivos:**
- Crear: `frontend/src/routes/auth/OnboardingPage.tsx`
- Crear: `frontend/src/components/onboarding/OnboardingSuccess.tsx`
- Modificar: `frontend/src/App.tsx` (agregar ruta `/onboarding`, redirect `/registro-padre`)

**Detalle:**

**OnboardingPage:**
- Estados: "loading" | "invalid" | "expired" | "wizard" | "success"
- Mount: extrae `?token=`, llama `useValidateToken(token)`
- Loading: skeleton/spinner
- Invalid/Expired: Card con mensaje descriptivo + link "Contactar al entrenador"
- Wizard: renderiza `OnboardingWizard` con `role` y `tokenData`
- onComplete: llama `useCompleteOnboarding()` mutation → "success"

**OnboardingSuccess:**
- Ícono de éxito (CheckCircle)
- "¡Cuenta creada exitosamente!"
- "Ya puedes seguir el progreso deportivo de [atleta]"
- Botón "Iniciar sesión" → `/login`
- Limpiar Zustand store (reset)

**Rutas App.tsx:**
```tsx
<Route path="/onboarding" element={<OnboardingPage />} />
<Route path="/registro-padre" element={<Navigate to="/onboarding" replace />} />
```

**Criterio de éxito:** Flujo completo funciona E2E: URL con token → wizard → registro → éxito.
**Dependencias:** Paso 11, Paso 15
**Estimado:** Mediano

---

## Fase E — Validación y Cleanup

### Paso 17: Tests E2E del flujo completo
**Agente:** `quality-engineer`
**Archivos:**
- Crear: `backend/tests/test_onboarding_consent.py`
- Verificar: flujo E2E manual con Docker Compose

**Escenarios a testear:**

| # | Escenario | Resultado esperado |
|---|---|---|
| 1 | Token válido → wizard completo → registro | User + ParentAthlete + ParentalConsent creados |
| 2 | Token expirado | Pantalla "enlace expirado" |
| 3 | Token ya usado | Pantalla "enlace ya utilizado" |
| 4 | Token inválido/inexistente | Pantalla "enlace inválido" |
| 5 | Email ya registrado | Error 409 con mensaje descriptivo |
| 6 | Consentimiento incompleto (falta obligatorio) | Validación frontend bloquea avance |
| 7 | Navegación atrás/adelante en wizard | Estado persistido correctamente |
| 8 | Cerrar browser y volver a URL | Recupera progreso desde localStorage |
| 9 | `/registro-padre` redirect | Redirige a `/onboarding` |
| 10 | Registro exitoso → login → dashboard padre | Flujo completo end-to-end |

**Criterio de éxito:** Todos los escenarios pasan.
**Dependencias:** Todos los pasos anteriores
**Estimado:** Mediano

---

## Diagrama de Dependencias

```
Fase A (Backend)                    Fase B (Backend)        Fase C (Frontend)
                                    
Paso 1 ──┬──→ Paso 2               Paso 7 (paralelo)       Paso 9 (paralelo)
          │                                                  │
          ├──→ Paso 4 ──→ Paso 5   Paso 8 (paralelo)       Paso 10 (paralelo)
          │                                                  │
Paso 3 ──┤                                                  Paso 11 (paralelo)
          │                                                  │
          └──→ Paso 6                                       Paso 12
                                                             │
                                    Fase D (Frontend)        │
                                                             ▼
                                    Paso 13 ──→ Paso 14 ──→ Paso 15 ──→ Paso 16
                                    
                                    Fase E (Validación)
                                    
                                    Paso 17 (depende de TODOS)
```

### Ejecución paralela óptima

| Ronda | Pasos | Agentes en paralelo |
|---|---|---|
| **Ronda 1** | 1, 3, 7, 8, 9, 10 | `fastapi-architect` × 3, `react-ui-engineer` × 2 |
| **Ronda 2** | 2, 4, 6, 11, 12, 13 | `fastapi-architect` × 3, `react-ui-engineer` × 2 |
| **Ronda 3** | 5, 14 | `fastapi-architect` × 1, `react-ui-engineer` × 1 |
| **Ronda 4** | 15, 16 | `react-ui-engineer` × 1 |
| **Ronda 5** | 17 | `quality-engineer` × 1 |

---

## Resumen de Archivos

### Crear (12 archivos nuevos)

| # | Archivo | Paso |
|---|---|---|
| 1 | `backend/app/models/parental_consent.py` | 1 |
| 2 | `backend/alembic/versions/xxx_add_parental_consents.py` | 2 |
| 3 | `backend/templates/email/parent_invite.html` | 7 |
| 4 | `frontend/src/schemas/onboarding.schema.ts` | 9 |
| 5 | `frontend/src/stores/onboarding-store.ts` | 10 |
| 6 | `frontend/src/hooks/onboarding/useOnboarding.ts` | 11 |
| 7 | `frontend/src/hooks/onboarding/index.ts` | 11 |
| 8 | `frontend/src/components/onboarding/OnboardingStepper.tsx` | 13 |
| 9 | `frontend/src/components/onboarding/onboarding-steps.ts` | 13 |
| 10 | `frontend/src/components/onboarding/steps/AccountStep.tsx` | 14 |
| 11 | `frontend/src/components/onboarding/steps/ParentProfileStep.tsx` | 14 |
| 12 | `frontend/src/components/onboarding/steps/ConsentStep.tsx` | 14 |
| 13 | `frontend/src/components/onboarding/steps/ConfirmStep.tsx` | 14 |
| 14 | `frontend/src/components/onboarding/OnboardingWizard.tsx` | 15 |
| 15 | `frontend/src/routes/auth/OnboardingPage.tsx` | 16 |
| 16 | `frontend/src/components/onboarding/OnboardingSuccess.tsx` | 16 |
| 17 | `backend/tests/test_onboarding_consent.py` | 17 |

### Modificar (7 archivos existentes)

| # | Archivo | Paso | Cambio |
|---|---|---|---|
| 1 | `backend/app/models/__init__.py` | 1 | Agregar import ParentalConsent |
| 2 | `backend/app/schemas/parent_invite.py` | 3 | Agregar schemas consent + extender request/response |
| 3 | `backend/app/services/invitations.py` | 4 | Extender consume_invite() con consent |
| 4 | `backend/app/routers/auth.py` | 5, 6 | Pasar consent a consume_invite, agregar role/club a response |
| 5 | `backend/app/routers/parent_athletes.py` | 8 | Fix URL onboarding |
| 6 | `frontend/src/api/parents.ts` | 12 | Actualizar tipos payload/response |
| 7 | `frontend/src/App.tsx` | 16 | Agregar ruta /onboarding, redirect /registro-padre |

---

## Fase 1B (Sprint siguiente) — Coach Onboarding

Una vez completada Fase 1A (padres), extender para coaches:

| Paso | Descripción | Agente |
|---|---|---|
| B1 | Crear modelo `CoachInvite` (o generalizar `Invitation` con campo `role`) | `fastapi-architect` |
| B2 | Endpoints: `POST /api/invitations/coach`, `POST /api/auth/coach-register` | `fastapi-architect` |
| B3 | Crear `CoachProfileStep.tsx` (certificaciones, experiencia, especialización) | `react-ui-engineer` |
| B4 | Agregar "coach" a `ONBOARDING_STEPS` config | `react-ui-engineer` |
| B5 | Template email `coach_invite.html` | `fastapi-architect` |
| B6 | UI admin: "Invitar entrenador" en panel de administración | `react-ui-engineer` |

**Decisión clave Fase 1B:** ¿Generalizar `ParentInvite` → `Invitation` con campo `role`? Sí, pero en Fase 1B para no romper lo existente ahora.

---

## Fase 2+ — Athlete Self-Onboarding

Para atletas mayores de 16 años que se registran solos:

| Paso | Descripción |
|---|---|
| C1 | Nuevo tipo de invitación: `athlete_self` |
| C2 | `AthleteProfileStep.tsx`: datos deportivos básicos |
| C3 | Consentimiento propio (>16) vs. parental (<16) — lógica por edad |
| C4 | Vinculación automática a club sin parent intermediario |
