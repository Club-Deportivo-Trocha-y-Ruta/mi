/**
 * PrivacyPage — Política de Tratamiento de Datos Personales
 *
 * Ruta pública: /privacidad (sin autenticación)
 * Cumplimiento: Ley 1581 de 2012 + Decreto 1377 de 2013 (Colombia)
 * Versión: 1.1 | 2026-05-06
 *
 * Cambios v1.0 → v1.1:
 *   - Recortadas finalidades a las efectivamente implementadas en Fase 1
 *     (datos básicos del atleta + antropometría/PHV).
 *   - Eliminadas menciones a inscripción en competencias, contacto de
 *     emergencia, documento de identidad, seguimiento de entrenamiento
 *     y transferencia a terceros (Intervals.icu, Google Sheets) — se
 *     reincorporarán cuando se implementen, con re-consentimiento.
 *   - Texto de antropometría: "control del crecimiento" en vez de
 *     "personalizar carga de entrenamiento" (no hay prescripción activa).
 */


// ---------------------------------------------------------------------------
// Constantes
// ---------------------------------------------------------------------------

const POLICY_VERSION = "1.1";
const POLICY_DATE = "6 de mayo de 2026";
const CONTACT_EMAIL = "clubtrochayruta@hotmail.com";
const CLUB_NAME = "Club Deportivo Trocha y Ruta";
const CITY = "Valle del Cauca, Colombia";

// ---------------------------------------------------------------------------
// Sub-componentes
// ---------------------------------------------------------------------------

function Section({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <details className="group border-b border-border/50 last:border-0">
      <summary
        className="flex cursor-pointer select-none items-center justify-between py-4 text-sm font-semibold text-charcoal marker:content-none hover:text-charcoal/70 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-link-blue"
        tabIndex={0}
      >
        {title}
        <svg
          className="h-4 w-4 shrink-0 text-mid-gray transition-transform duration-200 group-open:rotate-180"
          viewBox="0 0 16 16"
          fill="none"
          aria-hidden="true"
        >
          <path
            d="M4 6l4 4 4-4"
            stroke="currentColor"
            strokeWidth="1.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      </summary>
      <div className="pb-5 text-sm leading-relaxed text-mid-gray space-y-3">
        {children}
      </div>
    </details>
  );
}

function Pill({ children }: { children: React.ReactNode }) {
  return (
    <span className="inline-block rounded-full bg-light-gray px-2.5 py-0.5 text-xs font-medium text-charcoal">
      {children}
    </span>
  );
}

function Right({
  title,
  description,
}: {
  title: string;
  description: string;
}) {
  return (
    <div className="flex gap-3">
      <div className="mt-0.5 h-4 w-4 shrink-0 rounded-full bg-link-blue/10 flex items-center justify-center">
        <div className="h-1.5 w-1.5 rounded-full bg-link-blue" />
      </div>
      <div>
        <p className="text-sm font-medium text-charcoal">{title}</p>
        <p className="text-xs text-mid-gray mt-0.5">{description}</p>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Componente principal
// ---------------------------------------------------------------------------

export function PrivacyPage() {
  return (
    <div className="min-h-screen bg-white">
      {/* Header */}
      <div className="border-b border-border/50 bg-white px-4 py-4 sm:px-6">
        <div className="mx-auto flex max-w-2xl items-center justify-end">
          <div className="flex items-center gap-2">
            <Pill>v{POLICY_VERSION}</Pill>
            <span className="text-xs text-mid-gray">{POLICY_DATE}</span>
          </div>
        </div>
      </div>

      {/* Contenido */}
      <main className="mx-auto max-w-2xl px-4 py-8 sm:px-6" id="main-content">
        {/* Título */}
        <div className="mb-8">
          <h1
            className="font-display text-2xl text-charcoal"
          >
            Política de Tratamiento de Datos Personales
          </h1>
          <p className="mt-2 text-sm text-mid-gray">
            {CLUB_NAME} · {CITY}
          </p>
        </div>

        {/* Aviso breve (capa 1) */}
        <div
          className="mb-6 rounded-xl bg-light-gray px-4 py-4"
          style={{ boxShadow: "rgba(34, 42, 53, 0.05) 0px 1px 3px 0px" }}
          role="note"
          aria-label="Resumen de la política"
        >
          <p className="text-sm text-charcoal leading-relaxed">
            <strong className="font-semibold">Resumen:</strong> Recolectamos
            datos personales y de salud de los atletas y sus representantes
            legales para gestionar su participación en el club. El tratamiento
            cumple con la{" "}
            <strong className="font-medium">Ley 1581 de 2012</strong> y el
            Decreto 1377 de 2013. Para datos de menores exigimos autorización
            expresa de un padre o representante legal. Puedes ejercer tus
            derechos escribiéndonos a{" "}
            <a
              href={`mailto:${CONTACT_EMAIL}`}
              className="font-medium text-link-blue hover:underline underline-offset-2"
            >
              {CONTACT_EMAIL}
            </a>
            .
          </p>
        </div>

        {/* Secciones con acordeón nativo */}
        <div
          className="rounded-xl border border-border/60 bg-white px-5"
          style={{
            boxShadow:
              "rgba(19, 19, 22, 0.07) 0px 1px 5px -4px, rgba(34, 42, 53, 0.06) 0px 0px 0px 1px",
          }}
        >
          <Section title="1. Responsable del tratamiento">
            <p>
              <strong className="font-medium text-charcoal">
                {CLUB_NAME}
              </strong>{" "}
              actúa como responsable del tratamiento de los datos personales
              recolectados a través de esta plataforma.
            </p>
            <p>
              <strong className="font-medium text-charcoal">Contacto:</strong>{" "}
              <a
                href={`mailto:${CONTACT_EMAIL}`}
                className="text-link-blue hover:underline underline-offset-2"
              >
                {CONTACT_EMAIL}
              </a>
            </p>
            <p>
              <strong className="font-medium text-charcoal">Ubicación:</strong>{" "}
              {CITY}
            </p>
          </Section>

          <Section title="2. Datos que recolectamos">
            <p>Recolectamos únicamente los datos necesarios para las finalidades descritas:</p>
            <ul className="space-y-2 mt-2">
              <li className="flex gap-2">
                <span className="shrink-0 text-link-blue">·</span>
                <span>
                  <strong className="text-charcoal font-medium">Datos básicos del atleta:</strong>{" "}
                  nombre, apellido, fecha de nacimiento y sexo, necesarios para gestionar la
                  membresía del atleta en el club.
                </span>
              </li>
              <li className="flex gap-2">
                <span className="shrink-0 text-link-blue">·</span>
                <span>
                  <strong className="text-charcoal font-medium">
                    Antropometría y maduración biológica (datos sensibles):
                  </strong>{" "}
                  talla de pie, talla sentado, peso, envergadura y cálculo del Pico de Velocidad
                  de Crecimiento (PHV — Mirwald). Estos datos son de salud y requieren
                  consentimiento expreso.
                </span>
              </li>
              <li className="flex gap-2">
                <span className="shrink-0 text-link-blue">·</span>
                <span>
                  <strong className="text-charcoal font-medium">
                    Datos del representante legal:
                  </strong>{" "}
                  nombre, teléfono, correo electrónico y relación con el atleta.
                </span>
              </li>
            </ul>
            <p className="mt-2 text-xs text-mid-gray/80 italic">
              Principio de mínima recolección: no solicitamos datos que excedan lo necesario para
              las finalidades declaradas (Art. 4, Ley 1581/2012). En esta versión de la plataforma
              no recolectamos documentos de identidad, contactos de emergencia, sesiones de
              entrenamiento ni resultados de competencias. Cuando se incorporen estas
              funcionalidades solicitaremos un consentimiento nuevo.
            </p>
          </Section>

          <Section title="3. Finalidades del tratamiento">
            <ul className="space-y-2">
              <li className="flex gap-2">
                <span className="shrink-0 text-link-blue">·</span>
                Gestionar la membresía del atleta en el club.
              </li>
              <li className="flex gap-2">
                <span className="shrink-0 text-link-blue">·</span>
                Llevar control del crecimiento y la maduración biológica (PHV) del atleta y
                detectar señales de alerta nutricional o de desarrollo.
              </li>
              <li className="flex gap-2">
                <span className="shrink-0 text-link-blue">·</span>
                Comunicarse con los representantes legales sobre novedades del club y bienestar
                del atleta.
              </li>
            </ul>
          </Section>

          <Section title="4. Datos sensibles — antropometría y salud">
            <div
              className="flex gap-2.5 rounded-lg border border-amber-200 bg-amber-50 px-3.5 py-3"
              role="note"
            >
              <svg
                className="mt-0.5 h-4 w-4 shrink-0 text-amber-600"
                viewBox="0 0 16 16"
                fill="none"
                aria-hidden="true"
              >
                <path
                  d="M8 2L14 13H2L8 2z"
                  stroke="currentColor"
                  strokeWidth="1.5"
                  strokeLinejoin="round"
                />
                <path
                  d="M8 6v4M8 11.5v.5"
                  stroke="currentColor"
                  strokeWidth="1.5"
                  strokeLinecap="round"
                />
              </svg>
              <p className="text-xs text-amber-800">
                Los datos antropométricos (talla, peso, envergadura, PHV) se clasifican como
                datos sensibles de salud bajo la Ley 1581/2012 (Art. 5). Su tratamiento requiere{" "}
                <strong className="font-semibold">consentimiento expreso</strong> del representante
                legal. No puedes ser obligado a suministrarlos como condición para inscribirse al
                club, aunque son necesarios para la personalización del entrenamiento.
              </p>
            </div>
            <p className="mt-3">
              Estos datos se utilizan exclusivamente para calcular el estadio de maduración
              biológica (Pre-PHV, Circa-PHV, Post-PHV), llevar control del crecimiento del
              atleta a lo largo del tiempo y detectar señales de alerta (brote de crecimiento,
              riesgo nutricional). No se comparten con terceros.
            </p>
          </Section>

          <Section title="5. Tratamiento de datos de menores de edad">
            <p>
              Nuestros atletas son menores entre 10 y 15 años. Conforme a la Ley 1581/2012
              y las directrices del ICBF, el tratamiento de datos de menores está sujeto a
              protección especial:
            </p>
            <ul className="space-y-2 mt-2">
              <li className="flex gap-2">
                <span className="shrink-0 text-link-blue">·</span>
                <strong className="text-charcoal font-medium">
                  Autorización parental obligatoria:
                </strong>{" "}
                el padre, madre o representante legal debe otorgar autorización previa, expresa
                e informada antes de cualquier tratamiento.
              </li>
              <li className="flex gap-2">
                <span className="shrink-0 text-link-blue">·</span>
                <strong className="text-charcoal font-medium">Verificación:</strong> la
                autorización se captura mediante correo electrónico verificado del representante
                y queda registrada con marca de tiempo y versión de esta política.
              </li>
              <li className="flex gap-2">
                <span className="shrink-0 text-link-blue">·</span>
                <strong className="text-charcoal font-medium">Interés superior del menor:</strong>{" "}
                toda decisión sobre el tratamiento de datos considera ante todo el bienestar y
                la seguridad del atleta.
              </li>
              <li className="flex gap-2">
                <span className="shrink-0 text-link-blue">·</span>
                El representante puede revocar el consentimiento en cualquier momento desde
                su panel de usuario.
              </li>
            </ul>
          </Section>

          <Section title="6. Transferencia a terceros">
            <p>
              En esta versión de la plataforma{" "}
              <strong className="text-charcoal font-medium">no transferimos datos a terceros</strong>.
              Tampoco usamos los datos del atleta para entrenar modelos de inteligencia artificial
              ni para publicidad.
            </p>
            <p className="mt-2">
              Cuando integremos plataformas externas de análisis deportivo (por ejemplo,
              Intervals.icu) o herramientas de seguimiento de equipo, te lo informaremos y
              solicitaremos un consentimiento específico antes de compartir cualquier dato. Hasta
              entonces, los datos permanecen únicamente en nuestros sistemas.
            </p>
          </Section>

          <Section title="7. Tus derechos (Habeas Data)">
            <p>
              Como titular de los datos — o su representante legal — tienes los siguientes
              derechos reconocidos por la Ley 1581/2012:
            </p>
            <div className="mt-3 space-y-3">
              <Right
                title="Conocer"
                description="Saber qué datos tenemos sobre ti y cómo los usamos."
              />
              <Right
                title="Actualizar y rectificar"
                description="Corregir datos incompletos, inexactos o desactualizados."
              />
              <Right
                title="Suprimir"
                description="Solicitar la eliminación de tus datos cuando ya no sean necesarios, salvo obligación legal de retención."
              />
              <Right
                title="Revocar el consentimiento"
                description="Retirar la autorización otorgada. Puedes hacerlo desde tu panel de usuario o escribiéndonos."
              />
              <Right
                title="Portabilidad"
                description="Recibir tus datos en formato estructurado para trasladarlos a otro servicio."
              />
              <Right
                title="Presentar queja"
                description="Acudir a la Superintendencia de Industria y Comercio (SIC) si consideras que tus derechos han sido vulnerados."
              />
            </div>
          </Section>

          <Section title="8. Seguridad de los datos">
            <p>Aplicamos medidas técnicas y organizativas para proteger tus datos:</p>
            <ul className="space-y-2 mt-2">
              <li className="flex gap-2">
                <span className="shrink-0 text-link-blue">·</span>
                Comunicaciones cifradas con TLS (HTTPS) en todas las rutas.
              </li>
              <li className="flex gap-2">
                <span className="shrink-0 text-link-blue">·</span>
                Contraseñas almacenadas con bcrypt (sin texto plano).
              </li>
              <li className="flex gap-2">
                <span className="shrink-0 text-link-blue">·</span>
                Acceso restringido por roles (entrenador, padre, administrador).
              </li>
              <li className="flex gap-2">
                <span className="shrink-0 text-link-blue">·</span>
                En caso de incidente de seguridad que afecte tus datos, notificaremos a la SIC
                y a los titulares afectados en los plazos aplicables.
              </li>
            </ul>
          </Section>

          <Section title="9. Vigencia, versiones y actualizaciones">
            <p>
              Esta política entra en vigor el{" "}
              <strong className="text-charcoal font-medium">{POLICY_DATE}</strong> (versión{" "}
              <strong className="text-charcoal font-medium">{POLICY_VERSION}</strong>). Podemos
              actualizarla cuando cambie el marco legal o el tratamiento de datos.
            </p>
            <p>
              Si los cambios afectan las finalidades originalmente autorizadas, te notificaremos
              por correo y solicitaremos una nueva autorización antes de continuar el tratamiento.
            </p>
            <p>
              Cada autorización queda registrada con la versión de política vigente al momento
              de otorgarla.
            </p>
          </Section>
        </div>

        {/* Cómo ejercer tus derechos */}
        <div
          className="mt-6 rounded-xl border border-border/60 bg-white px-5 py-5"
          style={{
            boxShadow:
              "rgba(19, 19, 22, 0.07) 0px 1px 5px -4px, rgba(34, 42, 53, 0.06) 0px 0px 0px 1px",
          }}
        >
          <h2 className="text-sm font-semibold text-charcoal">
            Cómo ejercer tus derechos
          </h2>
          <p className="mt-2 text-sm text-mid-gray leading-relaxed">
            Escríbenos a{" "}
            <a
              href={`mailto:${CONTACT_EMAIL}`}
              className="font-medium text-link-blue hover:underline underline-offset-2"
            >
              {CONTACT_EMAIL}
            </a>{" "}
            indicando: (1) tu nombre completo, (2) documento de identidad, y (3) la solicitud
            específica (acceso, rectificación, supresión, portabilidad o revocación). Responderemos
            conforme a los plazos establecidos en la Ley 1581/2012.
          </p>
          <p className="mt-3 text-sm text-mid-gray">
            También puedes revocar tu consentimiento directamente desde tu{" "}
            <strong className="font-medium text-charcoal">panel de padre/acudiente</strong> sin
            necesidad de contactarnos.
          </p>
        </div>

        {/* Footer */}
        <div className="mt-8 pb-8 text-center">
          <p className="text-xs text-mid-gray">
            Versión {POLICY_VERSION} · {POLICY_DATE} · {CLUB_NAME}
          </p>
        </div>
      </main>
    </div>
  );
}
