# src/workers/tasks.py
"""
Tareas de Celery para procesar logs.
- process_log_task: Parsea el log, lo guarda en SQLite y
escribe en el FIFO si el nivel requiere alerta.
"""

import json
import os
from celery import Task
from .celery_config import celery_app
from src.core.config import config
from src.core.db import insert_log


class LogProcessingTask(Task):
    

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        print(f"   Tarea {task_id} falló: {exc}")
        print(f"   Args: {args}")
        print(f"   Error info: {einfo}")

    def on_success(self, retval, task_id, args, kwargs):
        pass  


@celery_app.task(
    base=LogProcessingTask,
    name='src.workers.tasks.process_log_task',
    bind=True,
    max_retries=3,
    default_retry_delay=5
)
def process_log_task(self, log_json: str):
    """
    Procesar un log: guardarlo en SQLite y enviar alerta si corresponde.
    """
    try:
        log = json.loads(log_json)

        log_id = insert_log(log)

        alert_sent = False
        if log.get('level') in config.ALERT_LEVELS:
            try:
                write_to_fifo(log)
                alert_sent = True
            except Exception as e:
                # FIFO no tiene lector
                print(f"No se pudo escribir en FIFO: {e}")

        return {
            'status': 'success',
            'log_id': log_id,
            'level': log.get('level'),
            'source': log.get('source'),
            'alert_sent': alert_sent
        }

    except json.JSONDecodeError as e:
        print(f"   JSON inválido: {e}")
        print(f"   Contenido: {log_json[:100]}...")
        return {
            'status': 'failed',
            'error': 'invalid_json',
            'message': str(e)
        }

    except Exception as e:
        print(f"Error procesando log: {e}")
        raise self.retry(exc=e)


def write_to_fifo(log: dict):
    """
    Escribir un log de alerta en el FIFO nombrado para que
    el Alert Manager lo consuma.

    La ruta del FIFO se lee desde config.FIFO_PATH (.env: FIFO_PATH).
    """
    fifo_path = config.FIFO_PATH

    # Crear FIFO si no existe
    if not fifo_path.exists():
        fifo_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.mkfifo(fifo_path)
            print(f"FIFO creado: {fifo_path}")
        except FileExistsError:
            pass

    try:
        fd = os.open(fifo_path, os.O_WRONLY | os.O_NONBLOCK)
        log_bytes = (json.dumps(log) + '\n').encode('utf-8')
        os.write(fd, log_bytes)
        os.close(fd)
        print(f"Alerta enviada a FIFO: [{log['level']}] {log['message'][:50]}")

    except BlockingIOError:
        print("FIFO no tiene lector activo, alerta descartada")
    except Exception as e:
        print(f"Error escribiendo en FIFO: {e}")
        raise


@celery_app.task(name='src.workers.tasks.health_check')
def health_check():
    """Verificar que los workers estén funcionando."""
    import platform
    import psutil

    return {
        'status': 'healthy',
        'hostname': platform.node(),
        'python_version': platform.python_version(),
        'celery_version': celery_app.VERSION,
        'cpu_percent': psutil.cpu_percent(),
        'memory_percent': psutil.virtual_memory().percent
    }


@celery_app.task(name='src.workers.tasks.cleanup_old_logs')
def cleanup_old_logs(days: int = 30):
    """
    Eliminar logs más viejos que x días.
    """
    from datetime import datetime, timedelta
    from src.core.db import get_db_write

    cutoff_date = (datetime.now() - timedelta(days=days)).isoformat()

    with get_db_write() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM logs WHERE timestamp < ?",
            (cutoff_date,)
        )
        count = cursor.fetchone()[0]

        cursor.execute(
            "DELETE FROM logs WHERE timestamp < ?",
            (cutoff_date,)
        )

    return {
        'deleted': count,
        'cutoff_date': cutoff_date
    }
