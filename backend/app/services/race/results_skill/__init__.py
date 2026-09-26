"""Motor de lectura offline de resultados (amendment 2026-09-26, User Story 1).

Este paquete es el único que aplica un ``ReadingProfile`` a un archivo
oficial de resultados fuera de la base de datos: ``masking`` produce la
vista enmascarada que ve un LLM al escribir el perfil
(``contracts/masked-view.md``), ``profile`` valida el esquema del perfil, y
``apply`` ejecuta el perfil sobre el archivo real (``contracts/
reading-profile.md``).

**Ningún router lo importa.** El único camino hacia la base de datos es
``app.services.race.import_staging`` llamando a ``apply.apply_profile`` y
guardando el resultado con ``staged_document.save`` — la fase 15 conecta ese
cableado; esto es solo el motor.

Privacidad: los módulos de este paquete leen archivos que contienen datos
de menores de edad. Ninguno registra en un log una fila, un nombre, un club
ni una ciudad — solo conteos, páginas y ordinales.
"""
from __future__ import annotations

#: Versión del motor de lectura (data-model.md §11.1,
#: ``race_import_staged_documents.engine_version``). Sube cuando cambia el
#: comportamiento de ``apply_profile`` de forma que un documento ya
#: aplicado con una versión anterior deba re-aplicarse para confiar en él.
ENGINE_VERSION = "1"
