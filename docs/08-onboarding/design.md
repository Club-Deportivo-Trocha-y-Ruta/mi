# Diseño: Flujo de Onboarding por Invitación

**Fecha:** 2026-04-15
**Basado en:** `docs/08-onboarding/research.md`
**Prerequisito:** `docs/06-parents/workflow.md` (módulo padres ya implementado)

---

## 1. Visión General

### Problema
El backend de invitaciones está completo pero el frontend tiene una página de registro plana (`ParentRegisterPage`) que no incluye consentimiento parental, no es multi-paso, y tiene route mismatch con la URL que genera el backend (`/onboarding` vs `/registro-padre`).

### Solución
Convertir el flujo en un **wizard multi-paso en `/onboarding`** que:
1. Valida token → infiere rol → muestra pasos específicos por rol
2. Incluye consentimiento parental obligatorio para padres
3. Es extensible para coaches (Fase 1B) y atletas (Fase 2+)

### Alcance por Fase

| Fase | Roles | Entregables |
|---|---|---|
| **1A (este sprint)** | Padre/Acudiente | Wizard 4 pasos, consentimiento, template email |
| **1B (próximo sprint)** | Coach/Entrenador | Paso "perfil profesional" + aceptar términos club |
| **2+** | Atleta (>16 años) | Perfil deportivo + consentimiento propio |

---

## 2. Arquitectura de Cambios

### 2.1 Lo que NO cambia (backend existente se preserva)

- `ParentInvite` modelo → se mantiene para padres
- `create_invite()`, `get_valid_invite()`, `consume_invite()` → sin cambios
- `POST /api/parent-athletes/invite` → sin cambios
- `GET /api/auth/invite/{token}` → se extiende respuesta
- `POST /api/auth/parent-register` → se extiende payload

### 2.2 Cambios Backend

#### 2.2.1 Extender `ParentInviteTokenValidation` response

Agregar campo `role` a la respuesta de validación de token para que el frontend sepa qué wizard mostrar:

```python
# backend/app/schemas/parent_invite.py
class ParentInviteTokenValidation(BaseModel):
    athlete_id: int
    athlete_name: str
    email: str
    expires_at: datetime
    valid: bool
    role: str = "parent"           # NUEVO: siempre "parent" para ParentInvite
    club_name: str = ""            # NUEVO: nombre del club para contexto
```

#### 2.2.2 Extender `ParentRegisterRequest` con consentimiento

```python
# backend/app/schemas/parent_invite.py
class ParentalConsentData(BaseModel):
    """Datos de consentimiento parental aceptados durante onboarding."""
    accept_data_collection: bool       # Recolección de datos del menor
    accept_training_tracking: bool     # Seguimiento deportivo y PHV
    accept_anthropometry: bool         # Mediciones antropométricas
    accept_third_party: bool = False   # Compartir con terceros (Intervals.icu, etc.)
    privacy_policy_version: str = "v1.0"

class ParentRegisterRequest(BaseModel):
    token: str
    first_name: str
    last_name: str
    password: str
    phone: str | None = None
    relationship_type: str = "acudiente"  # NUEVO: padre/madre/acudiente
    consent: ParentalConsentData          # NUEVO: consentimiento obligatorio
```

#### 2.2.3 Nuevo modelo `ParentalConsent`

```python
# backend/app/models/parental_consent.py
class ParentalConsent(Base):
    __tablename__ = "parental_consents"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    parent_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    athlete_id: Mapped[int] = mapped_column(ForeignKey("athletes.id"))
    consent_version: Mapped[str] = mapped_column(String(20))  # "v1.0"
    consented_at: Mapped[datetime] = mapped_column(DateTime)
    consent_method: Mapped[str] = mapped_column(String(50), default="digital_wizard")
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    data_collection: Mapped[bool] = mapped_column(Boolean, default=False)
    training_tracking: Mapped[bool] = mapped_column(Boolean, default=False)
    anthropometry: Mapped[bool] = mapped_column(Boolean, default=False)
    third_party_sharing: Mapped[bool] = mapped_column(Boolean, default=False)
    withdrawn_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    parent: Mapped["User"] = relationship("User")
    athlete: Mapped["Athlete"] = relationship("Athlete")
```

#### 2.2.4 Extender `consume_invite()` para registrar consentimiento

```python
# backend/app/services/invitations.py — agregar al final de consume_invite()
async def consume_invite(
    invite: ParentInvite,
    first_name: str,
    last_name: str,
    password: str,
    phone: str | None,
    relationship_type: str,      # NUEVO
    consent: ParentalConsentData, # NUEVO
    ip_address: str | None,      # NUEVO
    db: AsyncSession,
) -> User:
    # ... código existente crea user, club_member, parent_athlete ...

    # NUEVO: registrar consentimiento
    parental_consent = ParentalConsent(
        parent_user_id=new_user.id,
        athlete_id=invite.athlete_id,
        consent_version=consent.privacy_policy_version,
        consented_at=datetime.now(timezone.utc),
        consent_method="digital_wizard",
        ip_address=ip_address,
        data_collection=consent.accept_data_collection,
        training_tracking=consent.accept_training_tracking,
        anthropometry=consent.accept_anthropometry,
        third_party_sharing=consent.accept_third_party,
    )
    db.add(parental_consent)

    # Actualizar athlete.parental_consent_obtained
    athlete = await db.get(Athlete, invite.athlete_id)
    athlete.parental_consent_obtained = True
    athlete.parental_consent_date = datetime.now(timezone.utc)

    # ... commit existente ...
```

#### 2.2.5 Crear template email HTML

```
backend/templates/email/parent_invite.html
```

Template Jinja2 responsive con:
- Logo/nombre del club
- Saludo personalizado
- Nombre del atleta
- Botón CTA "Crear mi cuenta"
- URL de invitación
- Nota de expiración (72h)
- Footer con info del club

#### 2.2.6 Migración Alembic

```
alembic revision --autogenerate -m "add_parental_consents_table"
```

Crea tabla `parental_consents`. No modifica tablas existentes (consent fields en athletes ya existen).

### 2.3 Cambios Frontend

#### 2.3.1 Nueva ruta `/onboarding`

```typescript
// frontend/src/App.tsx
<Route path="/onboarding" element={<OnboardingPage />} />
// Mantener /registro-padre como redirect a /onboarding por compatibilidad
<Route path="/registro-padre" element={<Navigate to="/onboarding" replace />} />
```

#### 2.3.2 Arquitectura del Wizard

```
frontend/src/
├── routes/auth/
│   └── OnboardingPage.tsx              # Page wrapper: token validation + wizard
├── components/onboarding/
│   ├── OnboardingWizard.tsx            # Wizard container: stepper + navigation
│   ├── OnboardingStepper.tsx           # Visual stepper (shadcn primitivas)
│   ├── steps/
│   │   ├── AccountStep.tsx             # Email (readonly) + password + confirm
│   │   ├── ParentProfileStep.tsx       # Nombre, apellido, teléfono, parentesco
│   │   ├── ConsentStep.tsx             # Checkboxes de consentimiento parental
│   │   ├── CoachProfileStep.tsx        # (Fase 1B) Certificaciones, experiencia
│   │   └── ConfirmStep.tsx             # Resumen + botón enviar
│   └── OnboardingSuccess.tsx           # Pantalla de éxito post-registro
├── stores/
│   └── onboarding-store.ts            # Zustand persist: progreso del wizard
├── schemas/
│   └── onboarding.schema.ts           # Zod schemas por paso
└── hooks/onboarding/
    └── useOnboarding.ts               # Hook: validar token, submit registro
```

#### 2.3.3 Configuración declarativa de pasos

```typescript
// frontend/src/components/onboarding/onboarding-steps.ts

export type UserRole = "parent" | "coach" | "athlete";

export interface StepConfig {
  id: string;
  label: string;
  description: string;
  icon: LucideIcon;
  schema: ZodSchema;
  fields: string[];
  roles: UserRole[];
  component: React.ComponentType;
}

export const ONBOARDING_STEPS: StepConfig[] = [
  {
    id: "account",
    label: "Cuenta",
    description: "Crea tu contraseña de acceso",
    icon: KeyRound,
    schema: accountSchema,
    fields: ["password", "password_confirm"],
    roles: ["parent", "coach", "athlete"],
    component: AccountStep,
  },
  {
    id: "profile",
    label: "Perfil",
    description: "Datos personales",
    icon: UserCircle,
    schema: parentProfileSchema,
    fields: ["first_name", "last_name", "phone", "relationship_type"],
    roles: ["parent"],
    component: ParentProfileStep,
  },
  {
    id: "coach-profile",
    label: "Perfil Profesional",
    description: "Experiencia y certificaciones",
    icon: GraduationCap,
    schema: coachProfileSchema,
    fields: ["certifications", "experience_years", "specialization"],
    roles: ["coach"],
    component: CoachProfileStep,
  },
  {
    id: "consent",
    label: "Consentimiento",
    description: "Autorización para datos de tu hijo/a",
    icon: ShieldCheck,
    schema: consentSchema,
    fields: [
      "accept_data_collection",
      "accept_training_tracking",
      "accept_anthropometry",
      "accept_third_party",
    ],
    roles: ["parent"],
    component: ConsentStep,
  },
  {
    id: "confirm",
    label: "Confirmar",
    description: "Revisa y confirma tu registro",
    icon: CheckCircle2,
    schema: z.object({}), // sin validación adicional
    fields: [],
    roles: ["parent", "coach", "athlete"],
    component: ConfirmStep,
  },
];

// Runtime: filtrar por rol
export function getStepsForRole(role: UserRole): StepConfig[] {
  return ONBOARDING_STEPS.filter((s) => s.roles.includes(role));
}
```

#### 2.3.4 Schemas Zod por paso

```typescript
// frontend/src/schemas/onboarding.schema.ts

export const accountSchema = z
  .object({
    password: z
      .string()
      .min(8, "Mínimo 8 caracteres")
      .regex(/[A-Z]/, "Debe contener al menos una mayúscula")
      .regex(/[0-9]/, "Debe contener al menos un número"),
    password_confirm: z.string(),
  })
  .refine((d) => d.password === d.password_confirm, {
    message: "Las contraseñas no coinciden",
    path: ["password_confirm"],
  });

export const parentProfileSchema = z.object({
  first_name: z.string().min(1, "El nombre es requerido").trim(),
  last_name: z.string().min(1, "El apellido es requerido").trim(),
  phone: z
    .string()
    .regex(/^\+?[0-9]{7,13}$/, "Teléfono inválido")
    .optional()
    .or(z.literal("")),
  relationship_type: z.enum(["padre", "madre", "acudiente"], {
    required_error: "Selecciona el parentesco",
  }),
});

export const consentSchema = z.object({
  accept_data_collection: z.literal(true, {
    errorMap: () => ({
      message: "Debes autorizar la recolección de datos para continuar",
    }),
  }),
  accept_training_tracking: z.literal(true, {
    errorMap: () => ({
      message: "Debes autorizar el seguimiento deportivo para continuar",
    }),
  }),
  accept_anthropometry: z.literal(true, {
    errorMap: () => ({
      message: "Debes autorizar las mediciones antropométricas para continuar",
    }),
  }),
  accept_third_party: z.boolean().default(false), // opcional
});

// Schema combinado para type-safety del formulario completo
export const onboardingFormSchema = accountSchema
  .and(parentProfileSchema)
  .and(consentSchema);

export type OnboardingFormData = z.infer<typeof onboardingFormSchema>;
```

#### 2.3.5 Zustand Store

```typescript
// frontend/src/stores/onboarding-store.ts
import { create } from "zustand";
import { persist } from "zustand/middleware";

interface OnboardingState {
  currentStep: number;
  role: "parent" | "coach" | "athlete" | null;
  token: string | null;
  email: string | null;
  athleteName: string | null;
  clubName: string | null;
  formData: Record<string, unknown>;
  setStep: (step: number) => void;
  setTokenData: (data: {
    role: string;
    token: string;
    email: string;
    athleteName: string;
    clubName: string;
  }) => void;
  updateFormData: (data: Record<string, unknown>) => void;
  reset: () => void;
}

export const useOnboardingStore = create<OnboardingState>()(
  persist(
    (set) => ({
      currentStep: 0,
      role: null,
      token: null,
      email: null,
      athleteName: null,
      clubName: null,
      formData: {},
      setStep: (step) => set({ currentStep: step }),
      setTokenData: ({ role, token, email, athleteName, clubName }) =>
        set({ role: role as any, token, email, athleteName, clubName }),
      updateFormData: (data) =>
        set((s) => ({ formData: { ...s.formData, ...data } })),
      reset: () =>
        set({
          currentStep: 0,
          role: null,
          token: null,
          email: null,
          athleteName: null,
          clubName: null,
          formData: {},
        }),
    }),
    {
      name: "trocha-onboarding",
      // Limpiar si token expiró (72h desde almacenamiento)
    }
  )
);
```

#### 2.3.6 OnboardingPage — Page Wrapper

```typescript
// frontend/src/routes/auth/OnboardingPage.tsx

// Estados: "loading" | "invalid" | "expired" | "wizard" | "success"
//
// Flujo:
// 1. Extrae ?token= de URL
// 2. Llama GET /api/auth/invite/{token}
// 3. Si valid=true → muestra wizard con pasos filtrados por role
// 4. Si valid=false → muestra estado "invalid" o "expired"
// 5. Al completar wizard → POST /api/auth/parent-register → "success"
//
// El componente NO maneja formulario — delega al OnboardingWizard
```

#### 2.3.7 OnboardingWizard — Container

```typescript
// frontend/src/components/onboarding/OnboardingWizard.tsx

// Props: { role, tokenData, onComplete }
//
// Responsabilidades:
// 1. Filtra ONBOARDING_STEPS por rol
// 2. Renderiza OnboardingStepper (visual)
// 3. Wrappea en FormProvider (React Hook Form)
// 4. Maneja navegación: handleNext (trigger + persist) / handleBack
// 5. En último paso: handleSubmit → llama onComplete con formData completo
//
// handleNext = async () => {
//   const fields = visibleSteps[currentStep].fields;
//   const valid = await methods.trigger(fields);
//   if (!valid) return;
//   store.updateFormData(methods.getValues());
//   store.setStep(currentStep + 1);
// };
```

#### 2.3.8 ConsentStep — Paso de Consentimiento

```
Diseño UI del paso de consentimiento:

┌──────────────────────────────────────────────────┐
│  🛡️ Consentimiento Parental                      │
│                                                  │
│  Como padre/acudiente de [Nombre Atleta],        │
│  autorizas al Club Deportivo Trocha y Ruta a:    │
│                                                  │
│  ☐ Recolectar datos personales de mi hijo/a      │
│    (nombre, fecha de nacimiento, datos de         │
│     contacto de emergencia)                       │
│                                                  │
│  ☐ Realizar seguimiento deportivo                │
│    (sesiones de entrenamiento, resultados         │
│     competitivos, zonas de frecuencia cardíaca)   │
│                                                  │
│  ☐ Registrar mediciones antropométricas          │
│    (talla, peso, talla sentado para cálculo       │
│     de maduración biológica PHV)                  │
│                                                  │
│  ☐ Compartir datos con herramientas externas     │  ← Opcional
│    (Intervals.icu, Google Sheets — solo con       │
│     fines de análisis deportivo)                  │
│                                                  │
│  📄 Leer política de privacidad completa          │
│                                                  │
│  Los primeros 3 puntos son obligatorios para      │
│  la participación deportiva. Puedes revocar       │
│  tu consentimiento en cualquier momento desde     │
│  tu panel de padre.                               │
│                                                  │
│          [ ← Anterior ]    [ Siguiente → ]       │
└──────────────────────────────────────────────────┘
```

---

## 3. Flujo End-to-End Completo

```
┌─────────────────── COACH/ADMIN ───────────────────┐
│                                                    │
│  ParentDetailPage → ParentInviteManager            │
│  → "Invitar padre" → ingresa email                 │
│  → POST /api/parent-athletes/invite                │
│                                                    │
└────────────────────────┬───────────────────────────┘
                         │
                         ▼
┌─────────────────── BACKEND ───────────────────────┐
│                                                    │
│  1. Genera token (secrets.token_urlsafe(32))       │
│  2. Guarda en parent_invites (expires: 72h)        │
│  3. Renderiza parent_invite.html (Jinja2)          │
│  4. Envía email via NotificationService            │
│  5. Email contiene: {FRONTEND_URL}/onboarding?     │
│     token={raw_token}                              │
│                                                    │
└────────────────────────┬───────────────────────────┘
                         │
                         ▼
┌─────────────────── EMAIL ─────────────────────────┐
│                                                    │
│  "Hola! Has sido invitado a seguir el progreso    │
│   deportivo de [Atleta] en [Club].                 │
│                                                    │
│   [  Crear mi cuenta  ]  ← botón con link         │
│                                                    │
│   Este enlace expira en 72 horas."                 │
│                                                    │
└────────────────────────┬───────────────────────────┘
                         │ padre hace clic
                         ▼
┌─────────────────── FRONTEND ──────────────────────┐
│                                                    │
│  OnboardingPage monta                              │
│  → extrae ?token= de URL                           │
│  → GET /api/auth/invite/{token}                    │
│  → respuesta: { valid, role, email,                │
│                 athlete_name, club_name }           │
│                                                    │
│  Si valid=false → pantalla error/expirado          │
│  Si valid=true  → OnboardingWizard(role="parent")  │
│                                                    │
│  PASO 1: Cuenta                                    │
│  ├── Email (readonly, pre-rellenado)               │
│  ├── Contraseña + confirmación                     │
│  └── [Siguiente →]                                 │
│                                                    │
│  PASO 2: Perfil                                    │
│  ├── Nombre + Apellido                             │
│  ├── Teléfono (opcional)                           │
│  ├── Parentesco (padre/madre/acudiente)            │
│  └── [← Anterior] [Siguiente →]                   │
│                                                    │
│  PASO 3: Consentimiento                            │
│  ├── 3 checkboxes obligatorios                     │
│  ├── 1 checkbox opcional (terceros)                │
│  ├── Link a política de privacidad                 │
│  └── [← Anterior] [Siguiente →]                   │
│                                                    │
│  PASO 4: Confirmar                                 │
│  ├── Resumen de datos ingresados                   │
│  ├── "Serás vinculado como [parentesco] de         │
│  │    [atleta] en [club]"                          │
│  └── [← Anterior] [Crear cuenta]                  │
│                                                    │
│  → POST /api/auth/parent-register                  │
│    { token, first_name, last_name, password,       │
│      phone, relationship_type, consent: {...} }    │
│                                                    │
│  → OnboardingSuccess                               │
│    "¡Cuenta creada! Ya puedes seguir el progreso   │
│     de [atleta]."                                  │
│    [Ir a iniciar sesión]                           │
│                                                    │
└────────────────────────────────────────────────────┘
```

---

## 4. Modelo de Datos — Cambios

### Nueva tabla: `parental_consents`

| Columna | Tipo | Constraint | Descripción |
|---|---|---|---|
| `id` | INT | PK, AUTO | — |
| `parent_user_id` | INT | FK users.id, NOT NULL | Padre que otorga consentimiento |
| `athlete_id` | INT | FK athletes.id, NOT NULL | Atleta menor |
| `consent_version` | VARCHAR(20) | NOT NULL | Versión de política ("v1.0") |
| `consented_at` | DATETIME | NOT NULL | Timestamp UTC |
| `consent_method` | VARCHAR(50) | NOT NULL, DEFAULT "digital_wizard" | Método de verificación |
| `ip_address` | VARCHAR(45) | NULLABLE | IP del padre al aceptar |
| `data_collection` | BOOLEAN | NOT NULL, DEFAULT FALSE | Recolección datos personales |
| `training_tracking` | BOOLEAN | NOT NULL, DEFAULT FALSE | Seguimiento deportivo |
| `anthropometry` | BOOLEAN | NOT NULL, DEFAULT FALSE | Mediciones antropométricas |
| `third_party_sharing` | BOOLEAN | NOT NULL, DEFAULT FALSE | Compartir con terceros |
| `withdrawn_at` | DATETIME | NULLABLE | Fecha de revocación (NULL = vigente) |

**Índices:**
- `(parent_user_id, athlete_id)` — búsqueda rápida de consentimiento vigente
- `athlete_id` — búsqueda por atleta

### Tablas existentes — sin cambios estructurales

- `parent_invites` → sin cambios (token raw se mantiene por ahora; hash es mejora Fase 1B)
- `athletes` → `parental_consent_obtained` y `parental_consent_date` ya existen, se actualizan en `consume_invite()`
- `users`, `club_members`, `parent_athlete` → sin cambios

---

## 5. Endpoints API — Cambios

### Modificados

| Endpoint | Cambio |
|---|---|
| `GET /api/auth/invite/{token}` | Agregar `role` y `club_name` a respuesta |
| `POST /api/auth/parent-register` | Agregar `relationship_type` y `consent` al payload |

### Nuevos (Fase 1B — coaches)

| Método | Endpoint | Propósito |
|---|---|---|
| `POST` | `/api/invitations/coach` | Admin invita coach (nuevo router) |
| `POST` | `/api/auth/coach-register` | Coach completa registro desde invitación |

### Nuevos (Fase 2+ — consentimiento continuo)

| Método | Endpoint | Propósito |
|---|---|---|
| `GET` | `/api/consents/my-consents` | Padre ve sus consentimientos vigentes |
| `PUT` | `/api/consents/{id}/withdraw` | Padre revoca consentimiento |

---

## 6. Componentes shadcn/ui Necesarios

| Componente | Uso | Instalado? |
|---|---|---|
| `Card` | Wrapper del wizard | Verificar |
| `Button` | Navegación, submit | Verificar |
| `Input` | Campos de texto | Verificar |
| `Label` | Labels de formulario | Verificar |
| `Select` | Parentesco dropdown | Verificar |
| `Checkbox` | Consentimiento | Verificar |
| `Separator` | Entre secciones | Verificar |
| `Badge` | Indicador de paso actual | Verificar |
| `Alert` | Mensajes de error/info | Verificar |
| `Stepper` | No existe en shadcn — construir custom | N/A |

---

## 7. Template Email HTML

### `backend/templates/email/parent_invite.html`

**Estructura:**
```html
<!-- Jinja2 template, inline CSS para compatibilidad email -->
<!DOCTYPE html>
<html>
<body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
  
  <!-- Header con nombre del club -->
  <div style="background: #16a34a; color: white; padding: 20px; text-align: center;">
    <h1>Club Deportivo Trocha y Ruta</h1>
  </div>
  
  <!-- Contenido -->
  <div style="padding: 30px;">
    <h2>¡Hola!</h2>
    <p>Has sido invitado/a a seguir el progreso deportivo de 
       <strong>{{ athlete_first_name }}</strong> en 
       <strong>{{ club_name }}</strong>.</p>
    
    <p>Como padre o acudiente, podrás:</p>
    <ul>
      <li>Ver el desarrollo deportivo de tu hijo/a</li>
      <li>Consultar mediciones de crecimiento</li>
      <li>Recibir informes de progreso</li>
    </ul>
    
    <!-- CTA Button -->
    <div style="text-align: center; margin: 30px 0;">
      <a href="{{ invite_url }}" 
         style="background: #16a34a; color: white; padding: 14px 28px; 
                text-decoration: none; border-radius: 8px; font-weight: bold;">
        Crear mi cuenta
      </a>
    </div>
    
    <p style="color: #666; font-size: 14px;">
      Este enlace expira en 72 horas. Si no solicitaste esta invitación, 
      puedes ignorar este correo.
    </p>
  </div>
  
  <!-- Footer -->
  <div style="background: #f3f4f6; padding: 15px; text-align: center; font-size: 12px; color: #666;">
    <p>Club Deportivo Trocha y Ruta — Valle del Cauca, Colombia</p>
    <p>Ciclismo de montaña XCO juvenil</p>
  </div>
  
</body>
</html>
```

---

## 8. Consideraciones de Seguridad

| Área | Medida | Prioridad |
|---|---|---|
| Token en URL | Ya usa `token_urlsafe(32)` — seguro | ✅ OK |
| Token en DB | Raw actualmente. Hashear con SHA-256 en Fase 1B | 🟡 Media |
| CSRF | Endpoint público POST — proteger con CORS ya configurado | ✅ OK |
| Rate limiting | Sin implementar. Agregar en Fase 1B (slowapi + Redis) | 🟡 Media |
| XSS | React escapa por defecto. Template email usa Jinja2 autoescaping | ✅ OK |
| Datos menores | No exponer en logs/commits. Hook de privacidad activo | ✅ OK |
| Consentimiento | Registro con IP + timestamp + versión de política | ✅ Nuevo |

---

## 9. Testing Plan

| Tipo | Qué testear |
|---|---|
| **Unit** | Schemas Zod (cada paso), store Zustand (persist/reset) |
| **Integration** | `consume_invite()` con consentimiento, migración Alembic |
| **E2E** | Flujo completo: token → wizard → registro → login → dashboard |
| **Edge cases** | Token expirado, token usado, email duplicado, campos vacíos |

---

## 10. Decisiones Arquitectónicas

| Decisión | Alternativa descartada | Razón |
|---|---|---|
| Wizard multi-paso | Formulario único largo | UX progresiva, validación granular, extensible por rol |
| Zustand persist | Context API | Persistencia en localStorage, recuperación de progreso |
| Stepper custom | SmartStepper npm | Control total sobre UX, integración nativa con shadcn |
| `relationship_type` en registro | Siempre "acudiente" | Padres necesitan especificar parentesco real |
| Tabla `parental_consents` separada | Campos en `athletes` | Versionamiento, auditoría, múltiples padres por atleta |
| Template email Jinja2 | MJML | Stack existente ya usa Jinja2, menor complejidad |
