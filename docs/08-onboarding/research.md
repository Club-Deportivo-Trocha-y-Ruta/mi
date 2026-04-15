# Investigación: Flujo de Onboarding por Invitación

**Fecha:** 2026-04-15
**Profundidad:** deep
**Fuentes consultadas:** 24

## Resumen Ejecutivo

El sistema de invitaciones de Trocha y Ruta está **95% implementado en backend** pero tiene gaps críticos en frontend, templates de email, y consentimiento parental. La investigación web confirma que el stack actual (tokens opacos + FastAPI + React Hook Form) es el patrón correcto, pero se necesitan ajustes de seguridad (hash de tokens en DB) y un módulo de consentimiento parental completo dado que COPPA 2025 entra en vigencia el 22-abr-2026.

---

## 1. Estado Actual del Codebase

### Backend — Implementado ✅

| Componente | Archivo | Estado |
|---|---|---|
| Modelo `ParentInvite` | `backend/app/models/parent_invite.py` | ✅ Completo |
| Servicio invitaciones | `backend/app/services/invitations.py` | ✅ Completo |
| Router invitaciones | `backend/app/routers/parent_athletes.py` | ✅ Completo |
| Schemas Pydantic | `backend/app/schemas/parent_invite.py` | ✅ Completo |
| Auth: validar token | `backend/app/routers/auth.py` — `GET /api/auth/invite/{token}` | ✅ Completo |
| Auth: registro padre | `backend/app/routers/auth.py` — `POST /api/auth/parent-register` | ✅ Completo |
| Migración Alembic | `c3d4e5f6a7b8_add_parent_invites_and_consent.py` | ✅ Completo |
| NotificationService | `backend/app/services/notification/` | ✅ Completo |
| Template registry (PARENT_INVITE) | `backend/app/services/notification/template_registry.py` | ✅ Registrado |

### Endpoints Backend Disponibles

| Método | Endpoint | Propósito | Auth |
|---|---|---|---|
| `POST` | `/api/parent-athletes/invite` | Crear invitación + enviar email | Coach/Admin |
| `GET` | `/api/parent-athletes/invites?athlete_id={id}` | Listar invitaciones | Coach/Admin |
| `GET` | `/api/auth/invite/{token}` | Validar token | Público |
| `POST` | `/api/auth/parent-register` | Completar registro padre | Público |
| `GET` | `/api/parent-athletes/my-athletes` | Portal padre: mis atletas | Parent |

### Frontend — Parcialmente Implementado

| Componente | Archivo | Estado |
|---|---|---|
| `ParentRegisterPage` | `frontend/src/routes/auth/ParentRegisterPage.tsx` | ✅ Existe |
| `ParentInviteManager` | `frontend/src/components/parents/ParentInviteManager.tsx` | ✅ Existe |
| API client invitaciones | `frontend/src/api/parents.ts` | ✅ Existe |
| Hooks React Query | `frontend/src/hooks/parents/` | ✅ Existe |
| Ruta `/onboarding` | `frontend/src/App.tsx` | ❌ **No existe** |
| Template email HTML | `templates/email/parent_invite.html` | ❌ **No existe** |

### Gaps Críticos Identificados

| # | Issue | Severidad | Detalle |
|---|---|---|---|
| 1 | **Route mismatch** | 🔴 Alta | Backend genera URL `/onboarding?token=...` pero frontend tiene `/registro-padre` |
| 2 | **Template email faltante** | 🔴 Alta | `templates/email/parent_invite.html` referenciado pero no existe en disco |
| 3 | **Sin workflow de consentimiento** | 🟡 Media | Columnas `parental_consent_obtained/date` en DB pero sin UI ni endpoint |
| 4 | **Token sin hash en DB** | 🟡 Media | Token almacenado en crudo — debería hashearse (SHA-256) |
| 5 | **Sin onboarding multi-rol** | 🟡 Media | Solo soporta padres. Necesita extensibilidad para coaches y atletas futuros |
| 6 | **Sin rate limiting** | 🟢 Baja | Endpoints públicos sin protección contra abuso |

---

## 2. Investigación Web: Mejores Prácticas

### 2.1 Tokens de Invitación — Opacos > JWT

**Confianza: Alta (95%)**

Para invitaciones de un solo uso, tokens opacos superan a JWT:

| Criterio | JWT | Token Opaco |
|---|---|---|
| Revocación instantánea | ❌ Requiere blacklist | ✅ Eliminar de DB |
| Contenido legible | ⚠️ Base64 decodificable | ✅ Opaco |
| Single-use nativo | ❌ Requiere estado | ✅ Marcar en DB |
| Tamaño en URL | ❌ 300-500 bytes | ✅ 43 chars |

**Recomendación:** Mantener `secrets.token_urlsafe(32)` actual pero **hashear con SHA-256 antes de almacenar**. Si la tabla se compromete, los tokens raw no se pueden usar.

**Fuentes:**
- [ZITADEL — JWT vs Opaque Tokens](https://zitadel.com/blog/jwt-vs-opaque-tokens)
- [RFC 9700 — OAuth 2.0 Security Best Practices](https://datatracker.ietf.org/doc/rfc9700/)

### 2.2 Onboarding Multi-Rol — Bifurcación desde Token

**Confianza: Alta (88%)**

El patrón "persona-based onboarding" es óptimo: el token ya contiene el rol, el frontend infiere los pasos sin preguntar al usuario.

```
Token validado → rol = "parent" → pasos [cuenta, perfil, consentimiento, confirmación]
Token validado → rol = "coach"  → pasos [cuenta, perfil profesional, términos, confirmación]
Token validado → rol = "athlete" → pasos [cuenta, perfil deportivo, confirmación] (futuro)
```

**Arquitectura de pasos declarativa:**

```typescript
type StepConfig = {
  id: string;
  label: string;
  schema: ZodSchema;
  fields: string[];
  roles: UserRole[];
};

const ONBOARDING_STEPS: StepConfig[] = [
  { id: "account",    roles: ["parent", "coach", "athlete"], ... },
  { id: "profile",    roles: ["parent", "coach", "athlete"], ... },
  { id: "consent",    roles: ["parent"],                     ... },
  { id: "coach-bio",  roles: ["coach"],                      ... },
  { id: "confirm",    roles: ["parent", "coach", "athlete"], ... },
];

// Runtime: filtrar por rol
const visibleSteps = ONBOARDING_STEPS.filter(s => s.roles.includes(userRole));
```

**Fuentes:**
- [DesignerUp — 14 Types of Onboarding UX](https://designerup.co/blog/the-14-types-of-onboarding-ux-ui-used-by-top-apps-and-how-to-copy-them/)
- [Appcues — Choosing the Right Onboarding Pattern](https://www.appcues.com/blog/choosing-the-right-onboarding-ux-pattern)

### 2.3 Consentimiento Parental — COPPA 2025

**Confianza: Muy Alta (95%) — Crítico**

COPPA 2025 entra en vigencia **22 de abril de 2026** (en 7 días). Trocha y Ruta recolecta datos de atletas de 10-15 años → aplica.

> **Nota jurisdiccional:** COPPA es ley federal de EE.UU. Para Colombia, la Ley 1581 de 2012 (Habeas Data) y Ley 1098 (Código de Infancia) imponen obligaciones similares. Implementar estándares COPPA es best practice internacional.

**Requisitos para la app:**

1. **Aviso directo a padres** antes de recolectar datos del menor:
   - Qué datos se recolectan (nombre, fecha nacimiento, mediciones antropométricas)
   - Cómo se usan (seguimiento deportivo, cálculo PHV)
   - Si se comparten con terceros (Intervals.icu, Google Sheets)
   - Tiempo de retención

2. **Método de consentimiento verificable** recomendado:
   - **Digital wizard** con checkbox explícitos por categoría de datos (MVP)
   - **Text-Plus** (SMS OTP) como segundo factor (Fase 2)

3. **Tabla `parental_consents`** con versionamiento:

```python
class ParentalConsent(Base):
    __tablename__ = "parental_consents"
    id: Mapped[int]
    parent_user_id: Mapped[int]       # FK users
    athlete_id: Mapped[int]           # FK athletes
    consent_version: Mapped[str]      # "v1.0"
    consented_at: Mapped[datetime]
    consent_method: Mapped[str]       # "digital_wizard" | "signed_doc"
    ip_address: Mapped[str | None]
    data_uses_accepted: Mapped[dict]  # JSON: {training: true, third_party: false}
    withdrawn_at: Mapped[datetime | None]
```

4. **Controles parentales continuos:**
   - Ver qué datos se tienen del hijo
   - Revocar consentimiento
   - Solicitar eliminación

**Fuentes:**
- [FTC — COPPA Rule](https://www.ftc.gov/legal-library/browse/rules/childrens-online-privacy-protection-rule-coppa)
- [Loeb & Loeb — COPPA 2025 Amendments](https://www.loeb.com/en/insights/publications/2025/05/childrens-online-privacy-in-2025-the-amended-coppa-rule)
- [Securiti — FTC COPPA Final Rule](https://securiti.ai/ftc-coppa-final-rule-amendments/)

### 2.4 Stack Frontend para Wizard Multi-Paso

**Confianza: Alta (92%)**

Stack recomendado: **React Hook Form v7 + Zod + Zustand persist + shadcn/ui**

**Patrón clave — validación por paso con `trigger()`:**

```typescript
const handleNext = async () => {
  const currentStepFields = ONBOARDING_STEPS[currentStep].fields;
  const isValid = await methods.trigger(currentStepFields);
  if (!isValid) return;
  store.updateFormData(methods.getValues());
  setCurrentStep(prev => prev + 1);
};
```

**Persistencia:** `zustand/persist` + `localStorage` permite recuperar progreso si el usuario cierra el navegador. Verificar token válido antes de restaurar estado.

**Stepper UI:** shadcn/ui no tiene Stepper oficial. Opciones:
1. Construir stepper simple con primitivas shadcn (recomendado para control total)
2. SmartStepper npm package (compatible con RHF + Zod)

**Fuentes:**
- [LogRocket — Multi-Step Form RHF + Zod](https://blog.logrocket.com/building-reusable-multi-step-form-react-hook-form-zod/)
- [Build with Matija — Zustand + Zod + shadcn](https://www.buildwithmatija.com/blog/master-multi-step-forms-build-a-dynamic-react-form-in-6-simple-steps)
- [React Hook Form — Advanced Usage (trigger)](https://react-hook-form.com/advanced-usage)

### 2.5 Arquitectura FastAPI — Flujo E2E

**Confianza: Alta (90%)**

```
Coach/Admin                 Backend FastAPI              Frontend React
    |                            |                            |
    |-- POST /invite ----------->|                            |
    |                            |-- genera token + hash      |
    |                            |-- guarda hash en DB        |
    |                            |-- email con raw token ---->|
    |                            |                    clic en link
    |                            |<-- GET /invite/validate?token=xxx
    |                            |-- hash(token), busca en DB |
    |                            |-- retorna {email, role} -->|
    |                            |              wizard multi-paso
    |                            |<-- POST /invite/accept
    |                            |-- transacción atómica:     |
    |                            |   crea user + relaciones   |
    |                            |   registra consentimiento  |
    |                            |   marca token used         |
    |                            |-- retorna JWT sesión ----->|
    |                            |              redirige a dashboard
```

**Rate limiting recomendado (Redis + slowapi):**

| Endpoint | Límite | Por |
|---|---|---|
| `POST /invite` | 10/hora | Usuario autenticado |
| `GET /invite/validate` | 20/hora | IP |
| `POST /invite/accept` | 5/hora | IP |

**Fuentes:**
- [Scalekit — FastAPI Passwordless Auth](https://www.scalekit.com/blog/fastapi-passwordless-magic-link-otp-implementation)
- [Upstash — Rate Limiting FastAPI](https://upstash.com/docs/redis/tutorials/python_rate_limiting)

---

## 3. Contradicciones y Matices

- **Hash de tokens:** El codebase actual almacena tokens raw. La best practice es hashear. Sin embargo, el sistema actual ya funciona y el riesgo es bajo para un club deportivo local. **Recomendación:** implementar hash en esta iteración como mejora de seguridad.
- **COPPA jurisdicción:** COPPA es ley US, no colombiana. Pero la Ley 1581 colombiana tiene principios similares. Implementar estándar COPPA es over-engineering desde el punto de vista legal, pero es la mejor protección para menores.
- **Stepper component:** No hay consenso sobre usar librería vs construir propio. Para control total + integración con shadcn/ui, construir propio es preferible.

## 4. Gaps de Conocimiento

1. **Ley colombiana específica para apps deportivas de menores** — requiere consulta legal, no investigación web
2. **Proveedor SMTP/transaccional** (SendGrid, AWS SES, Resend) — decisión de infraestructura separada
3. **Flujo de onboarding para atletas >16 años** — no investigado en profundidad (Fase 2+)

## 5. Recomendaciones Priorizadas

### Prioridad 1 — Corregir lo roto
1. Fix route mismatch: unificar en `/onboarding`
2. Crear template email `parent_invite.html`
3. Convertir `ParentRegisterPage` en wizard multi-paso

### Prioridad 2 — Completar funcionalidad
4. Implementar consentimiento parental (tabla + UI)
5. Hash de tokens en DB (SHA-256)
6. Generalizar modelo de invitaciones para multi-rol

### Prioridad 3 — Hardening
7. Rate limiting en endpoints públicos
8. Dashboard de privacidad para padres
9. Persistencia de progreso del wizard (Zustand)

---

## Fuentes Completas

### Tokens y Seguridad
1. [ZITADEL — JWT vs Opaque Tokens](https://zitadel.com/blog/jwt-vs-opaque-tokens) — Alta
2. [Permit.io — Bearer Tokens Guide](https://www.permit.io/blog/a-guide-to-bearer-tokens-jwt-vs-opaque-tokens) — Alta
3. [RFC 9700 — OAuth 2.0 Security Best Practices](https://datatracker.ietf.org/doc/rfc9700/) — Muy Alta
4. [DZone — API Access Token Best Practices](https://dzone.com/articles/security-best-practices-for-managing-api-access-to) — Media

### FastAPI
5. [Scalekit — FastAPI Passwordless Auth](https://www.scalekit.com/blog/fastapi-passwordless-magic-link-otp-implementation) — Alta
6. [Upstash — Rate Limiting FastAPI](https://upstash.com/docs/redis/tutorials/python_rate_limiting) — Alta
7. [Bryan Anthonio — FastAPI Rate Limiter Redis](https://bryananthonio.com/blog/implementing-rate-limiter-fastapi-redis/) — Media

### React Multi-Step Forms
8. [LogRocket — Multi-Step Form RHF + Zod](https://blog.logrocket.com/building-reusable-multi-step-form-react-hook-form-zod/) — Alta
9. [Build with Matija — Zustand + Zod + shadcn](https://www.buildwithmatija.com/blog/master-multi-step-forms-build-a-dynamic-react-form-in-6-simple-steps) — Alta
10. [React Hook Form — Advanced Usage](https://react-hook-form.com/advanced-usage) — Muy Alta
11. [ClarityDev — Multistep Form](https://claritydev.net/blog/build-a-multistep-form-with-react-hook-form) — Media

### COPPA y Privacidad
12. [FTC — COPPA Rule](https://www.ftc.gov/legal-library/browse/rules/childrens-online-privacy-protection-rule-coppa) — Muy Alta
13. [Loeb & Loeb — COPPA 2025](https://www.loeb.com/en/insights/publications/2025/05/childrens-online-privacy-in-2025-the-amended-coppa-rule) — Alta
14. [Securiti — COPPA Amendments](https://securiti.ai/ftc-coppa-final-rule-amendments/) — Alta

### UX Onboarding
15. [Appcues — Onboarding UX Patterns](https://www.appcues.com/blog/choosing-the-right-onboarding-ux-pattern) — Alta
16. [DesignerUp — 14 Types of Onboarding UX](https://designerup.co/blog/the-14-types-of-onboarding-ux-ui-used-by-top-apps-and-how-to-copy-them/) — Alta
