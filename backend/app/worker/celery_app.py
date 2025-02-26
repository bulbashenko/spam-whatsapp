from celery import Celery
import logging
from app.core.config import settings

logger = logging.getLogger(__name__)

celery_app = Celery(
    "business_search_worker",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=["app.worker.tasks"]
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=3600,
    task_soft_time_limit=3300,
    worker_max_tasks_per_child=100,  # Reduced from 200 to minimize resource buildup
    worker_prefetch_multiplier=1,
    task_routes={
        "app.worker.tasks.*": {
            "queue": "business_search"
        }
    },
    task_default_queue="business_search",
    broker_connection_retry_on_startup=True,
    broker_connection_max_retries=10,
    task_annotations={
        "app.worker.tasks.*": {
            "rate_limit": "10/m"
        }
    },
    worker_pool="solo",  # Changed to solo to avoid event loop issues with asyncio
    worker_concurrency=1,   # Reduced to 1 to avoid race conditions with db connections
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_always_eager=False,
    broker_pool_limit=10,   # Set a reasonable pool limit instead of None
    broker_transport_options={
        'visibility_timeout': 3600,
        'socket_timeout': 30,
        'socket_connect_timeout': 30,
    }
)

@celery_app.task(bind=True)
def debug_task(self):
    """Debug task to verify Celery is working."""
    logger.info(f"Request: {self.request!r}")
    return "Debug task completed"

if __name__ == "__main__":
    celery_app.start()