from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import settings

# Pool real (AsyncAdaptedQueuePool, el default async de SQLAlchemy 2.x): las
# conexiones se reutilizan en vez de abrir una nueva por request.
#
# Historia: antes usábamos NullPool (una conexión por request) creyendo que
# pool_pre_ping no servía en Render free tier porque uvloop lanzaba RuntimeError
# en sockets muertos. Eso era incorrecto: ese RuntimeError ("Event loop is
# closed") es un artefacto de __del__/GC tras cerrarse el loop, NO un error de
# checkout. En una request viva, aiomysql lanza OperationalError 2006/2013 sobre
# una conexión cerrada por wait_timeout, y el dialecto la reconecta vía
# pool_pre_ping. Además, Render free tier TERMINA el proceso al dormir, así que
# tras un wake el pool arranca vacío (no hereda sockets muertos).
#
# NullPool abría >500 conexiones nuevas/hora bajo carga (cada request + cada
# nodo del grafo race-AI), disparando el límite de Hostinger
# `max_connections_per_hour` (500) → error 1226 y caída total. El pool elimina
# esa clase de error. Ver specs/ y docs de ops.
engine = create_async_engine(
    settings.database_url,
    pool_size=settings.db_pool_size,
    max_overflow=settings.db_max_overflow,
    pool_pre_ping=settings.db_pool_pre_ping,
    pool_recycle=settings.db_pool_recycle_seconds,
    pool_timeout=settings.db_pool_timeout,
    connect_args={
        "connect_timeout": 10,
    },
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    expire_on_commit=False,
)
