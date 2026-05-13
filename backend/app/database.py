from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.config import settings

engine = create_async_engine(
    settings.database_url,
    pool_size=2,
    max_overflow=3,
    pool_recycle=55,
    pool_pre_ping=True,
    pool_timeout=10,
    connect_args={
        "connect_timeout": 10,
    },
)

AsyncSessionLocal = sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)
