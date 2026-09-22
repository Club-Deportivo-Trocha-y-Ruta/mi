# Family notice — race history backfill (feature 044)

**Purpose.** Feature 044 (Copa Valle 2024–2025 backfill, `specs/044-race-history-backfill/`)
shows a parent their child's complete race history, including válidas raced *before*
the athlete joined the club (FR-040). Because that pre-joining data was not handed to
the club by the family, FR-041 requires an updated privacy-notice statement to be *in
force* before those pre-joining results are shown to a parent; until then they are
silently withheld (no "missing data" hint) and only post-joining results appear
(`backend/app/services/privacy.py` gates on `get_active_policy` / policy version, per
`research.md` R-09).

**Where this goes.** The Spanish paragraph below is a new section for the club's
privacy policy (`privacy_policies.content_html`), following the precedent of the v1.2
migration that added the AI-processing section
(`backend/alembic/versions/a2b3c4d5e6f7_add_policy_v1_2_ai_processing.py`): a new
Alembic migration deprecates the current policy row and inserts a new version (e.g.
`1.3`) whose `content_html` includes this section alongside the unchanged rest of the
policy.

**Activation.** Per R-09, this feature adds `RACE_HISTORY_FAMILY_POLICY_VERSION`
(default empty = gate closed, no pre-joining result is ever shown). Once the **owner**
publishes the new policy version through the existing policy flow, an operator sets
`RACE_HISTORY_FAMILY_POLICY_VERSION` to that version string (e.g. `1.3`). Only then do
pre-joining válidas appear in a parent's view — for coach and admin the gate never
applies. This is not a new per-family consent gate: no parent action is required
beyond the policy taking effect.

**Legal basis** (FR-015, `contracts/third-party-lock.md`): legitimate interest in a
sporting context, limited to situating the club's own athletes; publication on the
organiser's public results blog does not make the data "public data" under Ley 1581
Art. 3(g). Erasure of unlinked third-party competitors and retention of stored source
files are deferred to the next feature (FR-043) — worded below without overclaiming a
right that is not yet implemented.

---

## Texto para la política de privacidad (español neutro)

> ### Historial de resultados de competencia
>
> El club publica en la plataforma los resultados oficiales de la Copa Valle de tu
> hija o hijo, incluidos los resultados de válidas corridas **antes** de vincularse al
> club, cuando esa información ya fue publicada por la organización de la copa. Como
> representante, en tu panel solo ves los resultados de tu propio hijo o hija: nunca
> el nombre, club o ciudad de otro corredor. Los demás participantes de una categoría
> aparecen únicamente como cifras agrupadas (por ejemplo, cuántos corredores tuvo el
> campo o el tiempo mediano del grupo), nunca de forma individual. Esta información
> tampoco se envía a un proveedor de inteligencia artificial con el nombre de tu hijo
> o hija ni el de ningún otro corredor.
>
> Si tienes dudas sobre estos resultados, si algo no corresponde a tu hijo o hija, o
> si quieres solicitar una corrección, escríbenos a privacidad@trochyruta.com.
>
> El tratamiento de los datos de otros corredores que aparecen en los archivos
> oficiales —incluida su eliminación cuando corresponda y el tiempo de conservación de
> los archivos fuente— se resuelve mediante un proceso interno del club que estamos
> terminando de definir; esta política se actualizará cuando esté listo.

*(148 palabras de texto para familias.)*
