# src/workers/celery_config.py


from celery import Celery
from src.core.config import config


# Crear aplicación Celery usando la URL de Redis del config
celery_app = Celery(
    'logstream_workers',
    broker=config.REDIS_URL,
    backend=config.REDIS_URL,
    include=['src.workers.tasks']
)

celery_app.conf.update(
    # Serialización
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',

    # Timezone
    timezone=config.CELERY_TIMEZONE,
    enable_utc=True,

    # Tareas
    task_track_started=True,
    task_time_limit=config.CELERY_TASK_TIME_LIMIT,
    task_soft_time_limit=config.CELERY_TASK_SOFT_TIME_LIMIT,

    # Resultados
    result_expires=config.CELERY_RESULT_EXPIRES,

    # Workers
    worker_prefetch_multiplier=config.CELERY_WORKER_PREFETCH_MULTIPLIER,
    worker_max_tasks_per_child=config.CELERY_WORKER_MAX_TASKS_PER_CHILD,

    # Cola por defecto
    task_default_queue='log_processing',
    task_default_exchange='log_processing',
    task_default_routing_key='log_processing',

    # Rutas de tareas
    task_routes={
        'src.workers.tasks.process_log_task': {'queue': 'log_processing'},
    },

    # Logging
    worker_log_format='[%(asctime)s: %(levelname)s/%(processName)s] %(message)s',
    worker_task_log_format=(
        '[%(asctime)s: %(levelname)s/%(processName)s]'
        '[%(task_name)s(%(task_id)s)] %(message)s'
    ),
)

celery_app.autodiscover_tasks(['src.workers'])


if __name__ == '__main__':
    celery_app.start()
