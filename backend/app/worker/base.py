from celery import Task
import asyncio
import logging
from contextlib import asynccontextmanager
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from app.core.database import AsyncSessionLocal

logger = logging.getLogger(__name__)

class DatabaseTask(Task):
    
    _db: Optional[AsyncSession] = None
    
    def __init__(self):
        super().__init__()
    
    def after_return(self, *args, **kwargs):
        if self._db is not None:
            try:
                loop = asyncio.get_event_loop()
                if not loop.is_closed():
                    loop.run_until_complete(self._db.close())
                self._db = None
            except Exception as e:
                logger.error(f"Error during cleanup: {str(e)}")
        super().after_return(*args, **kwargs)
    
    def get_loop(self):
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        return loop
    
    @asynccontextmanager
    async def db_session(self) -> AsyncSession:
        if self._db is None or self._db.is_active:
            self._db = AsyncSessionLocal()
        
        try:
            async with self._db as session:
                yield session
                await session.commit()
        except Exception as e:
            await session.rollback()
            logger.error(f"Database session error: {str(e)}")
            raise
        finally:
            await session.close()
            self._db = None

    def run_async(self, coro):
        loop = self.get_loop()
        try:
            return loop.run_until_complete(coro)
        except Exception as e:
            logger.error(f"Error in run_async: {str(e)}")
            raise