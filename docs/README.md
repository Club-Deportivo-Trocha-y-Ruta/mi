# Documentos de referencia

Este directorio debe contener los dos documentos fundamentales del club:

1. **`marco-teorico.md`** — Marco Teórico-Metodológico para el Entrenamiento de Ciclistas Juveniles XCO (10-15 años). Copiar aquí el contenido de `investigacion.md`.

2. **`plan-entrenamiento-2026.md`** — Plan de Entrenamiento XCO Copa Valle 2026 (20 abril – 31 diciembre). Exportar el contenido del .docx a markdown y colocarlo aquí.

Estos documentos son referenciados por el `CLAUDE.md` principal y por los skills y agentes del proyecto. Claude Code los lee automáticamente cuando necesita fundamentar una decisión de entrenamiento.

## Cómo agregar los documentos

```bash
# Opción 1: Copiar directamente los archivos markdown
cp /ruta/a/investigacion.md docs/marco-teorico.md
cp /ruta/a/plan-entrenamiento.md docs/plan-entrenamiento-2026.md

# Opción 2: Si tienes el .docx, convertir con pandoc
pandoc Plan_Entrenamiento_XCO_Copa_Valle_2026.docx -o docs/plan-entrenamiento-2026.md
```
