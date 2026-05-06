from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

from app.config import settings

# NullPool: evita RuntimeError de uvloop en TCPTransport cerrado tras sleep
# de Render free tier. pool_pre_ping no detecta el error como disconnect
# porque es RuntimeError nativo, no OperationalError.
engine = create_async_engine(
    settings.database_url,
    poolclass=NullPool,
)

AsyncSessionLocal = sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)
