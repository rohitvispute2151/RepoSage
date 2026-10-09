"""Celery application configuration with Redis broker.

Defines asynchronous worker queues, beat schedules, and task settings.
"""

from celery import Celery

from reposage.config import settings

celery_app = Celery(
    "reposage",
    broker=settings.redis_url,
    backend=settings.redis_url,
)

celery_app.conf.update(
    worker_pool="threads",
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    broker_connection_retry_on_startup=False,
    broker_connection_timeout=0.2,
    redis_socket_connect_timeout=0.2,
    # Periodic background lease reaper schedule (runs every 15 seconds)
    beat_schedule={
        "reaper-every-15-seconds": {
            "task": "reposage.workers.tasks.reaper_task",
            "schedule": 15.0,
        },
    },
)

from celery.signals import worker_process_init


@worker_process_init.connect
def fix_worker_process_optimizations(*args, **kwargs):
    """Ensure worker optimizations and task tables are initialized in spawned worker processes.

    Resolves `ValueError: not enough values to unpack (expected 3, got 0)` in Celery fast_trace_task
    on platforms using the spawn multiprocessing start method (such as macOS and Windows).
    """
    from celery.app import trace

    trace.setup_worker_optimizations(celery_app)

