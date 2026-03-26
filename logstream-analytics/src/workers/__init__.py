# src/workers/__init__.py


from .celery_config import celery_app
from .tasks import process_log_task

__all__ = ['celery_app', 'process_log_task']
