import logging
from typing import Any

from sqlalchemy import event
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import settings

logger = logging.getLogger(__name__)

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

def _is_closed_transport_error(err: BaseException) -> bool:
    return isinstance(err, RuntimeError) and (
        "handler is closed" in str(err) or "Event loop is closed" in str(err)
    )


@event.listens_for(engine.sync_engine, "handle_error")
def _uvloop_closed_is_disconnect(ctx: "Any") -> None:
    if _is_closed_transport_error(ctx.original_exception):
        ctx.is_disconnect = True
        logger.debug("uvloop RuntimeError clasificado como disconnect; pool descartará la conexión.")


def _wrap_ping_closed_transport(dialect: "Any") -> None:
    """El pre-ping de SQLAlchemy (``_do_ping_w_event``) solo atrapa errores
    DBAPI: el ``RuntimeError`` de uvloop sobre un socket que Hostinger ya
    cerró se escapaba sin pasar por ``handle_error`` y la request entera
    reventaba con 500 en vez de reconectar. Devolver ``False`` hace que el
    pool invalide la conexión y abra una nueva, que es lo que pre-ping
    promete."""
    original_ping = dialect.do_ping

    def _do_ping(dbapi_connection: "Any") -> bool:
        try:
            return original_ping(dbapi_connection)
        except RuntimeError as err:
            if _is_closed_transport_error(err):
                logger.debug("pre-ping sobre transporte cerrado; el pool reconectará.")
                return False
            raise

    dialect.do_ping = _do_ping


_wrap_ping_closed_transport(engine.sync_engine.dialect)


AsyncSessionLocal = async_sessionmaker(
    engine,
    expire_on_commit=False,
)
