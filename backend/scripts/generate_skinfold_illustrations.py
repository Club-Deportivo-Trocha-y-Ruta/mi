"""Prompts, generación y exportación de las ilustraciones de pliegues cutáneos.

Contexto
========
El asistente de captura de pliegues (feature 046) muestra, por cada sitio
de medición, un diagrama que indica dónde marcar y cómo tomar el pliegue.
Los SVG dibujados a mano eran demasiado toscos, así que se reemplazaron por
ilustraciones generadas con IA.

Cómo se generó la serie que está en el repo
===========================================
La llave de ``backend/.env`` (``AI_API_KEY``) NO tiene cuota de imágenes
(todos los modelos de imagen responden 429 con ``limit: 0``: capa gratuita
sin facturación), así que el modo de generación por API de este script no
se pudo usar. La serie se generó a mano en Gemini web pegando los prompts de
este archivo (``STYLE`` + ``SITE[sitio]``, con el prefijo "Generate an
image. ") y se exportó con ``--export``. Imágenes elegidas y ajustes:

    sitio         original (en --src)    recorte previo al cuadrado
    triceps       triceps_2.png          ninguno
    biceps        biceps_1.png           (0,120,700,820): brazo y hombro más grandes
    subscapular   subscapular_2.jpeg     ninguno
    medial_calf   medial_calf_2.jpeg     ninguno
    iliac_crest   iliac_crest_1.png      (505,0,1024,1024): solo la vista lateral
    supraspinale  supraspinale_1.png     (3,0,512,1024): solo la figura completa

Nota: la figura de ``supraspinale`` no muestra manos ni plicómetro (el panel
con la maniobra se descartó); solo el sitio, la marca y la línea guía.

Salidas de ``--export`` (cuadradas, fondo blanco; se limpia el ruido casi
blanco del generador):

* ``frontend/src/assets/skinfolds/<sitio>.webp``: 768 px, calidad 82.
* ``backend/templates/documents/pdf/diagrams/img/skinfold_<sitio>.png``:
  600 px, PNG optimizado.

Uso
===
    cd backend
    source .venv/bin/activate

    # Generar candidatos por API (requiere llave con cuota de imágenes):
    python scripts/generate_skinfold_illustrations.py \\
        --site all --candidates 3 --out /tmp/skinfold_imgs
    # Regenerar un sitio sin pisar candidatos previos (numera desde 4):
    python scripts/generate_skinfold_illustrations.py \\
        --site subscapular --candidates 3 --start 4

    # Exportar las imágenes elegidas (están en --src) a frontend y PDF:
    python scripts/generate_skinfold_illustrations.py --export --src /tmp/skinfold_imgs

Requisitos y privacidad
=======================
* La llave se lee de ``backend/.env`` dentro del proceso; nunca se imprime
  ni se escribe a disco.
* Los prompts describen un maniquí sin rostro ni rasgos identificables; no
  se envía ningún dato de deportistas.
* La generación reintenta con backoff exponencial ante 429 / 5xx, y falla
  de inmediato si el 429 es de cuota cero.

Historial de cambios a los prompts
==================================
* Ronda 2, ``STYLE``: "EXACTLY TWO simple muted blue-gray hands, never
  more"; el calibrador pasó de "slim silver ... flat parallel jaws" a
  "clearly recognizable ... (Harpenden style: round dial body with two long
  flat jaws)" sostenido por la mano derecha del examinador; y la región
  medida pasó a "fills most of the frame" (antes: centrada con márgenes).
  El original está en ``STYLE_INICIAL``.
* Ronda 3, ``SITE["subscapular"]`` y ``SITE["medial_calf"]`` reescritos
  (dirección explícita del pliegue subescapular, "hacia afuera" desde la
  columna; pantorrilla en la masa muscular, no en la tibia, sin cuerpo
  sobre la rodilla). Los originales están en ``SITE_INICIAL``.
* Los demás sitios (triceps, biceps, iliac_crest, supraspinale) no cambiaron.
"""

from __future__ import annotations

import argparse
import os
import random
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import numpy as np
from dotenv import dotenv_values
from google import genai
from google.genai import errors as genai_errors
from google.genai import types
from PIL import Image

BACKEND_DIR = Path(__file__).resolve().parent.parent
FRONTEND_ASSETS = BACKEND_DIR.parent / "frontend" / "src" / "assets" / "skinfolds"
PDF_IMAGES = BACKEND_DIR / "templates" / "documents" / "pdf" / "diagrams" / "img"

# Exportación: sitio -> (archivo elegido en --src, recorte previo (x0,y0,x1,y1)
# sobre el original, zona a blanquear tras el recorte (y0,y1,x0,x1)).
EXPORT_SOURCES: dict[str, tuple[str, tuple[int, int, int, int] | None, tuple[int, int, int, int] | None]] = {
    "triceps": ("triceps_2.png", None, None),
    "biceps": ("biceps_1.png", (0, 120, 700, 820), None),
    "subscapular": ("subscapular_2.jpeg", None, None),
    "medial_calf": ("medial_calf_2.jpeg", None, None),
    "iliac_crest": ("iliac_crest_1.png", (505, 0, 1024, 1024), None),
    # El original trae dos paneles: queda solo la figura izquierda y se borra
    # el borde de la mano del panel derecho que se cuela en el recorte.
    "supraspinale": ("supraspinale_1.png", (3, 0, 512, 1024), (480, 600, 500, 509)),
}
FRONTEND_SIZE = 768
FRONTEND_QUALITY = 82
FRONTEND_MAX_BYTES = 120 * 1024
PDF_SIZE = 600

# Preferencia de modelos: el "pro" de mayor calidad primero, luego flash.
MODEL_PREFERENCE = (
    "gemini-3-pro-image",
    "gemini-3-pro-image-preview",
    "gemini-3.1-flash-image",
    "gemini-3.1-flash-image-preview",
    "gemini-2.5-flash-image",
)

MAX_RETRIES = 5

STYLE = """Clean flat instructional medical illustration in a modern vector style, for a field guide used by a youth cycling coach. The measured person is a smooth, light-gray, faceless mannequin figure: no facial features, no hair, no nipples, no genital or anatomical detail, gender-neutral, lean athletic build, wearing plain dark-gray fitted athletic shorts only where the lower body is visible. The examiner is shown as EXACTLY TWO simple muted blue-gray hands, never more (no arms beyond the wrist, no sleeves with logos). Plain pure-white background, thin dark-charcoal outlines, soft minimal shading. Exactly one accent color: teal (#0E9FB0), used only for the anatomical landmark (a small cross inside a circle drawn on the skin) and for thin dashed guide lines. The examiner's left thumb and index finger pinch and lift a double layer of skin (the skinfold) about 1 cm from the landmark; the examiner's right hand holds a single clearly recognizable skinfold caliper (Harpenden style: round dial body with two long flat jaws) whose jaws clamp that fold exactly at the landmark, jaws perpendicular to the fold. Absolutely no text, letters, numbers, arrows with labels, rulers with numbers, logos or watermarks anywhere in the image. Square 1:1 composition; the measured body region fills most of the frame. This image is one of a consistent series of six; keep identical style, colors, line weight and mannequin across the series."""

# STYLE de la especificación original (ronda 1). Reemplazado por el de arriba:
# dos manos exactas, calibrador tipo Harpenden en la mano derecha y región
# medida a mayor tamaño (ver historial en el docstring).
STYLE_INICIAL = """Clean flat instructional medical illustration in a modern vector style, for a field guide used by a youth cycling coach. The measured person is a smooth, light-gray, faceless mannequin figure: no facial features, no hair, no nipples, no genital or anatomical detail, gender-neutral, lean athletic build, wearing plain dark-gray fitted athletic shorts only where the lower body is visible. The examiner is shown only as two simple muted blue-gray hands (no arms beyond the wrist, no sleeves with logos). Plain pure-white background, thin dark-charcoal outlines, soft minimal shading. Exactly one accent color: teal (#0E9FB0), used only for the anatomical landmark (a small cross inside a circle drawn on the skin) and for thin dashed guide lines. The examiner's left thumb and index finger pinch and lift a double layer of skin (the skinfold) about 1 cm from the landmark; a single slim silver skinfold caliper with flat parallel jaws clamps that fold exactly at the landmark, jaws perpendicular to the fold. Absolutely no text, letters, numbers, arrows with labels, rulers with numbers, logos or watermarks anywhere in the image. Square 1:1 composition, the measured region large and centered with generous white margins. This image is one of a consistent series of six; keep identical style, colors, line weight and mannequin across the series."""

SITE = {
    "triceps": """Site: TRICEPS skinfold. View from directly behind the mannequin, cropped from the top of the shoulder to just below the elbow, showing the mannequin's RIGHT upper arm (which appears on the viewer's RIGHT side in this back view) hanging relaxed and straight at the side, palm facing the thigh. A thin teal dashed line runs down the back of the arm from the bony tip of the shoulder (acromion) to the point of the elbow (olecranon); the teal landmark sits on the back midline of the upper arm exactly at the midpoint of that line. The skinfold is VERTICAL, parallel to the long axis of the arm, lifted just above the landmark; the caliper jaws are horizontal, clamping the fold at the landmark.""",
    "biceps": """Site: BICEPS skinfold. View from directly in front of the mannequin, cropped from the top of the shoulder to just below the elbow, showing the mannequin's RIGHT upper arm (which appears on the viewer's LEFT side in this front view) hanging relaxed at the side with the palm facing forward. The teal landmark sits on the front of the upper arm over the most prominent part of the biceps muscle, at the same height as the midpoint between shoulder tip and elbow, indicated by a short horizontal teal dashed line across the arm at that height. The skinfold is VERTICAL, parallel to the long axis of the arm, lifted just above the landmark; the caliper jaws are horizontal, clamping the fold at the landmark.""",
    "subscapular": """Site: SUBSCAPULAR skinfold. View from directly behind the mannequin's upper torso only, cropped from the base of the neck to the waist, arms relaxed at the sides; no legs, no shorts. The outline of the RIGHT shoulder blade is drawn faintly; in this back view it is on the viewer's RIGHT. The teal landmark sits just below the lowest tip of that shoulder blade. A thin teal dashed line passes through the landmark going from UPPER-LEFT (toward the spine) to LOWER-RIGHT (toward the right flank, the viewer's right edge), at 45 degrees; the pinched skinfold lies along that line, so the fold runs downward and OUTWARD, away from the spine. The examiner's left hand pinches the fold just above-left of the landmark; the examiner's right hand holds the caliper, whose jaws close on the fold exactly at the landmark, perpendicular to the dashed line. Exactly two hands.""",
    "medial_calf": """Site: MEDIAL CALF skinfold. Close-up of the mannequin's RIGHT lower leg only, from just above the knee to the foot; the right foot rests on a low plain box so the knee is bent at 90 degrees and the shin is vertical. The view is from the INNER side of the leg, so we see the rounded calf muscle bulging toward the viewer's side behind the shin. The teal landmark sits on the inner surface of the calf muscle (NOT on the shin bone) at the calf's widest point, with a short horizontal teal dashed line across the calf at that height. The examiner's left hand pinches a VERTICAL skinfold on the calf just above the landmark; the examiner's right hand holds the dial caliper whose jaws, horizontal, close on that fold exactly at the landmark. Exactly two hands. No measuring tape, no body above the knee.""",
    "iliac_crest": """Site: ILIAC CREST skinfold. Pure side view of the mannequin's RIGHT side, cropped from the armpit to the upper thigh; the right arm is folded across the chest so the side of the trunk is fully exposed. The top edge of the hip bone (iliac crest) is drawn faintly as a gentle curve. A vertical teal dashed line drops from the middle of the armpit (mid-axillary line). The teal landmark sits where that vertical line meets the top of the hip bone, on the side of the body. The skinfold is almost HORIZONTAL, running along the top of the hip bone with a slight downward tilt toward the front of the body; the caliper jaws are nearly vertical, clamping the fold at the landmark.""",
    "supraspinale": """Site: SUPRASPINALE skinfold. Front three-quarter view of the mannequin's RIGHT lower trunk (which appears on the viewer's LEFT), cropped from the lower chest to the upper thigh, arms relaxed away from the body. The bony point at the front of the hip (anterior superior iliac spine) is marked faintly. A thin teal dashed line runs from that front hip point diagonally up to the front edge of the armpit. The teal landmark sits on that line about 5 to 7 cm above the front hip point, clearly higher and more toward the front than the side of the hip. The skinfold is DIAGONAL, running downward and inward toward the groin at about 45 degrees; the caliper jaws are perpendicular to that fold, clamping it at the landmark.""",
}


# Textos de sitio de la especificación original que se reescribieron en la
# ronda 3 (subescapular y pantorrilla salían con pliegue/orientación erróneos).
SITE_INICIAL = {
    "subscapular": """Site: SUBSCAPULAR skinfold. View from directly behind the mannequin's upper torso, cropped from the base of the neck to the lower ribs, arms relaxed at the sides. The outline of the RIGHT shoulder blade (scapula) is drawn faintly on the back; the right shoulder blade is on the viewer's RIGHT in this back view. The teal landmark sits just below the lowest tip (inferior angle) of the right shoulder blade. The skinfold is DIAGONAL, running downward and outward toward the side of the body at about 45 degrees, along the natural skin lines; a teal dashed guide line shows that 45-degree direction. The caliper jaws are perpendicular to that diagonal fold, clamping it at the landmark.""",
    "medial_calf": """Site: MEDIAL CALF skinfold. The mannequin stands with the RIGHT foot resting on a low plain box so the right knee is bent at 90 degrees and the calf is relaxed. View from the INNER (medial) side of the right lower leg, cropped from just above the knee to the foot. The teal landmark sits on the inner side of the calf at its widest girth, with a short horizontal teal dashed line around the calf at that maximal girth. The skinfold is VERTICAL, parallel to the long axis of the lower leg, lifted just above the landmark; the caliper jaws are horizontal, clamping the fold at the landmark.""",
}


def build_prompt(site: str) -> str:
    return STYLE + "\n\n" + SITE[site]


def load_client() -> genai.Client:
    """Crea el cliente leyendo la llave de ``backend/.env`` sin exponerla."""
    values = dotenv_values(BACKEND_DIR / ".env")
    key = (
        values.get("AI_API_KEY")
        or values.get("RACE_AI_API_KEY")
        or os.environ.get("AI_API_KEY")
        or os.environ.get("RACE_AI_API_KEY")
    )
    if not key:
        sys.exit("No se encontró AI_API_KEY / RACE_AI_API_KEY en backend/.env")
    return genai.Client(api_key=key)


def pick_model(client: genai.Client, requested: str | None) -> str:
    """Devuelve el mejor modelo de imagen disponible (o el pedido)."""
    if requested:
        return requested
    available = {m.name.removeprefix("models/") for m in client.models.list()}
    for name in MODEL_PREFERENCE:
        if name in available:
            return name
    candidates = sorted(n for n in available if "image" in n)
    if not candidates:
        sys.exit("No hay modelos de imagen disponibles para esta llave.")
    return candidates[-1]


def _retryable(exc: Exception) -> bool:
    if isinstance(exc, genai_errors.APIError):
        code = getattr(exc, "code", None)
        if code == 429:
            # "limit: 0" = la llave no tiene cuota de imágenes (sin facturación):
            # reintentar no sirve.
            return "limit: 0" not in str(exc)
        return isinstance(code, int) and 500 <= code < 600
    return isinstance(exc, (ConnectionError, TimeoutError))


def generate_one(client: genai.Client, model: str, site: str, out_path: Path) -> str:
    """Genera un candidato y lo guarda como PNG. Devuelve un mensaje de estado."""
    config = types.GenerateContentConfig(
        response_modalities=["IMAGE"],
        image_config=types.ImageConfig(aspect_ratio="1:1"),
    )
    prompt = build_prompt(site)
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = client.models.generate_content(
                model=model, contents=prompt, config=config
            )
        except Exception as exc:  # noqa: BLE001 - se reclasifica abajo
            if attempt < MAX_RETRIES and _retryable(exc):
                wait = min(60.0, 2.0**attempt) + random.uniform(0, 1.5)
                time.sleep(wait)
                continue
            code = getattr(exc, "code", "")
            reason = "cuota de imágenes = 0 (¿falta facturación?)" if "limit: 0" in str(exc) else ""
            return f"ERROR {out_path.name}: {type(exc).__name__} {code} {reason}".strip()
        for cand in response.candidates or []:
            for part in (cand.content.parts if cand.content else None) or []:
                inline = getattr(part, "inline_data", None)
                if inline and inline.data:
                    out_path.write_bytes(inline.data)
                    return f"ok {out_path.name}"
        # Sin imagen (filtro de seguridad o respuesta solo texto): reintenta.
        if attempt < MAX_RETRIES:
            time.sleep(2.0 * attempt)
            continue
        return f"SIN IMAGEN {out_path.name}"
    return f"ERROR {out_path.name}"


def _to_white_rgb(path: Path) -> Image.Image:
    """Abre la imagen y compone el alfa sobre blanco."""
    im = Image.open(path).convert("RGBA")
    bg = Image.new("RGBA", im.size, (255, 255, 255, 255))
    bg.alpha_composite(im)
    return bg.convert("RGB")


def _square_white(im: Image.Image) -> Image.Image:
    """Rellena con blanco hasta cuadrado, centrando la imagen."""
    w, h = im.size
    side = max(w, h)
    canvas = Image.new("RGB", (side, side), (255, 255, 255))
    canvas.paste(im, ((side - w) // 2, (side - h) // 2))
    return canvas


def export_site(site: str, src_dir: Path) -> str:
    """Recorta, cuadra y exporta un sitio a frontend (WebP) y PDF (PNG)."""
    filename, crop, clear = EXPORT_SOURCES[site]
    im = _to_white_rgb(src_dir / filename)
    if crop:
        im = im.crop(crop)
    if clear:
        arr = np.asarray(im).copy()
        y0, y1, x0, x1 = clear
        arr[y0:y1, x0:x1] = 255
        im = Image.fromarray(arr)
    im = _square_white(im)
    # Ruido casi blanco (254/250) del generador: a blanco puro.
    arr = np.asarray(im).copy()
    arr[arr.min(axis=2) >= 249] = 255
    im = Image.fromarray(arr)

    FRONTEND_ASSETS.mkdir(parents=True, exist_ok=True)
    PDF_IMAGES.mkdir(parents=True, exist_ok=True)

    webp_path = FRONTEND_ASSETS / f"{site}.webp"
    small = im.resize((FRONTEND_SIZE, FRONTEND_SIZE), Image.LANCZOS)
    quality = FRONTEND_QUALITY
    while True:
        small.save(webp_path, "WEBP", quality=quality, method=6)
        if webp_path.stat().st_size <= FRONTEND_MAX_BYTES or quality <= 60:
            break
        quality -= 4

    png_path = PDF_IMAGES / f"skinfold_{site}.png"
    im.resize((PDF_SIZE, PDF_SIZE), Image.LANCZOS).save(png_path, "PNG", optimize=True)
    return (
        f"{site}: {webp_path.stat().st_size // 1024} KB webp (q{quality}), "
        f"{png_path.stat().st_size // 1024} KB png"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--site", default="all", help="id del sitio o 'all'")
    parser.add_argument("--candidates", type=int, default=3)
    parser.add_argument("--start", type=int, default=1, help="primer índice de candidato")
    parser.add_argument("--out", default="/tmp/skinfold_imgs")
    parser.add_argument("--model", default=None, help="fuerza un modelo concreto")
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument(
        "--export",
        action="store_true",
        help="exporta las imágenes elegidas (--src) a frontend y PDF; no llama a la API",
    )
    parser.add_argument("--src", default="/tmp/skinfold_imgs", help="carpeta con los originales elegidos")
    args = parser.parse_args()

    if args.export:
        targets = list(EXPORT_SOURCES) if args.site == "all" else [args.site]
        for site in targets:
            print(export_site(site, Path(args.src)))
        return

    if args.site != "all" and args.site not in SITE:
        sys.exit(f"Sitio desconocido: {args.site}. Opciones: {', '.join(SITE)} | all")
    sites = list(SITE) if args.site == "all" else [args.site]

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    client = load_client()
    model = pick_model(client, args.model)
    print(f"Modelo: {model}")

    jobs = [
        (site, out_dir / f"{site}_{n}.png")
        for site in sites
        for n in range(args.start, args.start + args.candidates)
    ]
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(generate_one, client, model, s, p) for s, p in jobs]
        for fut in as_completed(futures):
            print(fut.result(), flush=True)


if __name__ == "__main__":
    main()
