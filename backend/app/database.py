from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

from app.config import settings

# NullPool: abre una conexión por request y la cierra al finalizar.
# Requerido en Render free tier: el container duerme tras ~15 min, cerrando
# los sockets TCP. pool_pre_ping no ayuda porque uvloop lanza RuntimeError
# (no OperationalError) en conexiones muertas, evitando que SQLAlchemy las
# recicle. NullPool elimina esta clase de error completamente.
engine = create_async_engine(
    settings.database_url,
    poolclass=NullPool,
    connect_args={
        "connect_timeout": 10,
    },
)

AsyncSessionLocal = sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)
