# Fixtures GPX sintéticas (e2e)

Todo archivo `.gpx` en este directorio es **sintético** — generado con
`backend/tests/helpers/gpx_builder.py` (feature 043, perfil de circuito).
Nunca se sube aquí la grabación real de un entrenamiento o carrera: es un
dato personal del coach y esta carpeta se versiona en git.

## Regenerar `course_3laps.gpx` y `course_reduced.gpx`

Desde `backend/`, con el venv activo:

```bash
.venv/bin/python -c "
from pathlib import Path
from tests.helpers.gpx_builder import circle_gpx

out = Path('../frontend/e2e/fixtures')
(out / 'course_3laps.gpx').write_bytes(
    circle_gpx(radius_m=640, points=200, laps=3, jitter_m=5)
)
(out / 'course_reduced.gpx').write_bytes(
    circle_gpx(radius_m=320, points=120, laps=1)
)
"
```

Ver `specs/043-race-course-profile/contracts/gpx-processing.md` §4 para el
detalle de las firmas del builder (`circle_gpx`, `out_and_back_gpx`,
`figure_eight_gpx`) y los casos que cada fixture debe cubrir.
