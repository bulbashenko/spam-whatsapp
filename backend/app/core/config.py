from typing import Optional
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    API_V1_STR: str = "/api/v1"
    PROJECT_NAME: str = "Business Search API"
    
    SECRET_KEY="REMOVED": str = "secret"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 8
    
    GOOGLE_PLACES_API_KEY="REMOVED": str
    
    POSTGRES_SERVER: str
    POSTGRES_USER: str
    POSTGRES_PASSWORD="REMOVED": str
    POSTGRES_DB: str
    POSTGRES_PORT: str
    
    @property
    def POSTGRES_DATABASE_URL(self) -> str:
        return f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD="REMOVED"}@{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
    
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_PASSWORD="REMOVED": Optional[str] = None
    REDIS_SOCKET_TIMEOUT: int = 30
    REDIS_SOCKET_CONNECT_TIMEOUT: int = 30
    
    @property
    def CELERY_BROKER_URL(self) -> str:
        auth = f":{self.REDIS_PASSWORD="REMOVED"}@" if self.REDIS_PASSWORD="REMOVED" else "@"
        return f"redis://{auth}{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"
    
    @property
    def CELERY_RESULT_BACKEND(self) -> str:
        return self.CELERY_BROKER_URL
    
    # Celery specific settings
    CELERY_TASK_SOFT_TIME_LIMIT: int = 3300  # 55 minutes
    CELERY_TASK_TIME_LIMIT: int = 3600  # 1 hour
    CELERY_WORKER_MAX_TASKS_PER_CHILD: int = 200
    CELERY_WORKER_PREFETCH_MULTIPLIER: int = 1
    
    ELASTICSEARCH_HOST: str = "localhost"
    ELASTICSEARCH_PORT: int = 9200
    
    class Config:
        case_sensitive = True
        env_file = ".env"


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()