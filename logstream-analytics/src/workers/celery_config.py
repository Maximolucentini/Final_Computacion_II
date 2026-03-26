# src/workers/celery_config.py
"""
Configuración de Celery para LogStream Analytics.


"""

from celery import Celery
import os
from pathlib import Path

# Cargar variables de entorno
try:
    from dotenv import load_dotenv
    env_path = Path(__file__).parent.parent.parent / '.env'
    load_dotenv(env_path)
except ImportError:
    pass  # dotenv es opcional


# Configuración de Redis
REDIS_HOST = os.getenv('REDIS_HOST', 'localhost')
REDIS_PORT = os.getenv('REDIS_PORT', '6379')
REDIS_DB = os.getenv('REDIS_DB', '0')

# URL de conexión Redis
BROKER_URL = f'redis://{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}'
RESULT_BACKEND = f'redis://{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}'


# Crear aplicación Celery
celery_app = Celery(
    'logstream_workers',
    broker=BROKER_URL,
    backend=RESULT_BACKEND,
    include=['src.workers.tasks']  # Módulo donde están las tareas
)


# Configuración de Celery
celery_app.conf.update(
    # Serialización
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    
    # Timezone
    timezone='America/Argentina/Mendoza',
    enable_utc=True,
    
    # Tareas
    task_track_started=True,
    task_time_limit=300,  # 5 minutos máximo por tarea
    task_soft_time_limit=240,  # 4 minutos soft limit
    
    # Resultados
    result_expires=3600,  # Resultados expiran en 1 hora
    
    # Workers
    worker_prefetch_multiplier=4,  # Cuántas tareas toma cada worker
    worker_max_tasks_per_child=1000,  # Reiniciar worker cada 1000 tareas
    
    # Cola por defecto
    task_default_queue='log_processing',
    task_default_exchange='log_processing',
    task_default_routing_key='log_processing',
    
    # Rutas de tareas (qué cola usa cada tarea)
    task_routes={
        'src.workers.tasks.process_log_task': {'queue': 'log_processing'},
    },
    
    # Logging
    worker_log_format='[%(asctime)s: %(levelname)s/%(processName)s] %(message)s',
    worker_task_log_format='[%(asctime)s: %(levelname)s/%(processName)s][%(task_name)s(%(task_id)s)] %(message)s',
)


# busca tareas automáticamente)
celery_app.autodiscover_tasks(['src.workers'])


if __name__ == '__main__':
    celery_app.start()
