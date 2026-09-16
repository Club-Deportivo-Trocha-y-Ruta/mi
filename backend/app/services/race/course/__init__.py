"""Servicios de perfil de circuito (GPX) para válidas de Copa Valle.

``gpx_processing.py`` es puro y síncrono: procesa en memoria los bytes de un
GPX subido por el coach y no realiza ningún I/O (sin filesystem, sin red, sin
logging de contenido) — el archivo original nunca se persiste. ``service.py``
es la capa async que valida y persiste variantes de circuito y las
configuraciones de vueltas por categoría de cada válida.
"""
