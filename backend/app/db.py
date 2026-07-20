from dataclasses import dataclass
from typing import cast

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import QueuePool

from app.observability import bind_db_pool_in_use


@dataclass
class Database:
    engine: AsyncEngine
    session_factory: async_sessionmaker[AsyncSession]

    async def dispose(self) -> None:
        await self.engine.dispose()


def create_database(url: str) -> Database:
    engine = create_async_engine(url)
    pool = cast(QueuePool, engine.sync_engine.pool)
    bind_db_pool_in_use(pool.checkedout)
    return Database(
        engine=engine,
        session_factory=async_sessionmaker(engine, expire_on_commit=False),
    )
