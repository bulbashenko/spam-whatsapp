from celery import Task
import asyncio
import logging
from contextlib import asynccontextmanager
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, Coroutine, Any

from app.core.database import AsyncSessionLocal

logger = logging.getLogger(__name__)

class DatabaseTask(Task):
    
    _db: Optional[AsyncSession] = None
    
    def __init__(self):
        super().__init__()
    
    def after_return(self, *args, **kwargs):
        if self._db is not None:
            try:
                loop = self.get_loop()
                if not loop.is_closed():
                    loop.run_until_complete(self._db.close())
                self._db = None
            except Exception as e:
                logger.error(f"Error during cleanup: {str(e)}")
        super().after_return(*args, **kwargs)
    
    def get_loop(self):
        try:
            loop = asyncio.get_event_loop()
            if loop.is_closed():
                raise RuntimeError("Event loop is closed")
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        return loop
    
    @asynccontextmanager
    async def db_session(self) -> AsyncSession:
        """Get a database session within the same event loop context"""
        session = AsyncSessionLocal()
        
        try:
            yield session
            await session.commit()
        except Exception as e:
            await session.rollback()
            logger.error(f"Database session error: {str(e)}")
            raise
        finally:
            await session.close()

    def run_async(self, coro: Coroutine[Any, Any, Any]) -> Any:
        """Run a coroutine in the correct event loop"""
        loop = self.get_loop()
        
        try:
            if loop.is_running():
                # If we're already in a running loop, create a new one to avoid issues
                new_loop = asyncio.new_event_loop()
                try:
                    asyncio.set_event_loop(new_loop)
                    return new_loop.run_until_complete(coro)
                finally:
                    new_loop.close()
                    asyncio.set_event_loop(loop)
            else:
                return loop.run_until_complete(coro)
        except Exception as e:
            logger.error(f"Error in run_async: {str(e)}")
            raise