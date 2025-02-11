from typing import Optional
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    API_V1_STR: str = "/api/v1"
    PROJECT_NAME: str = "Business Search API"
    
    SECRET_KEY="REMOVED": str = "secret"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 8
    
    GOOGLE_PLACES_API_KEY="REMOVED": str = "AIzaSyBvt51CUpwsZsykn-zgfwYX7zqZfwGtUJY"
    
    SQLITE_DATABASE_URL: str = "sqlite:///./business_search.db"
    
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    
    CELERY_BROKER_URL: str = "redis://localhost:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/0"
    
    ELASTICSEARCH_HOST: str = "localhost"
    ELASTICSEARCH_PORT: int = 9200
    
    class Config:
        case_sensitive = True
        env_file = ".env"


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()