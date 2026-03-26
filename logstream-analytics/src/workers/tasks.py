# src/workers/tasks.py
"""
Tareas de Celery para procesar logs.

Tarea principal:
- process_log_task: Saca log de Redis, lo guarda en SQLite
"""

import json
import os
from pathlib import Path
from celery import Task
from .celery_config import celery_app
from src.core.db import insert_log
from src.core.redis_client import get_redis_client


# Configuración
FIFO_PATH = Path(__file__).parent.parent.parent / 'data' / 'alert_pipe'
ALERT_LEVELS = ['ERROR', 'CRITICAL']  # Niveles que generan alertas


class LogProcessingTask(Task):
    
    
    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """Llamado cuando la tarea falla."""
        print(f"   Tarea {task_id} falló: {exc}")
        print(f"   Args: {args}")
        print(f"   Error info: {einfo}")
    
    def on_success(self, retval, task_id, args, kwargs):
        """Llamado cuando la tarea tiene éxito."""
        # Silencioso en éxito (demasiado verbose sino)
        pass


@celery_app.task(
    base=LogProcessingTask,
    name='src.workers.tasks.process_log_task',
    bind=True,
    max_retries=3,
    default_retry_delay=5  # Reintentar después de 5 segundos
)
def process_log_task(self, log_json):
    """
    Procesar un log: guardarlo en SQLite y enviar alerta si es necesario.
    """
    try:
        # 1. Parsear JSON
        log = json.loads(log_json)
        
        # 2. Guardar en SQLite (con Redis lock automático)
        log_id = insert_log(log)
        
        # 3. Si es alerta (ERROR o CRITICAL), escribir en FIFO
        if log.get('level') in ALERT_LEVELS:
            try:
                write_to_fifo(log)
            except Exception as e:
                # No fallar la tarea si FIFO no funciona
                print(f"No se pudo escribir en FIFO: {e}")
        
        # 4. Retornar info del procesamiento
        return {
            'status': 'success',
            'log_id': log_id,
            'level': log.get('level'),
            'source': log.get('source'),
            'alert_sent': log.get('level') in ALERT_LEVELS
        }
        
    except json.JSONDecodeError as e:
        # JSON inválido, no reintentar
        print(f"   JSON inválido: {e}")
        print(f"   Contenido: {log_json[:100]}...")
        return {
            'status': 'failed',
            'error': 'invalid_json',
            'message': str(e)
        }
        
    except Exception as e:
        # Otros errores: reintentar
        print(f"Error procesando log: {e}")
        
        # Reintentar tarea
        raise self.retry(exc=e)

# Escribir log en FIFO para que Alert Manager lo procese.

def write_to_fifo(log):
    
    # Crear FIFO si no existe
    if not FIFO_PATH.exists():
        FIFO_PATH.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.mkfifo(FIFO_PATH)
            print(f"FIFO creado: {FIFO_PATH}")
        except FileExistsError:
            pass  # Ya existe
    
    # Escribir en FIFO (bloqueante hasta que alguien lea)
    try:
        # Abrir en modo no-bloqueante para evitar deadlock
        fd = os.open(FIFO_PATH, os.O_WRONLY | os.O_NONBLOCK)
        
        # Convertir log a JSON
        log_json = json.dumps(log)
        log_bytes = (log_json + '\n').encode('utf-8')
        
        # Escribir
        os.write(fd, log_bytes)
        os.close(fd)
        
        print(f"Alerta enviada a FIFO: [{log['level']}] {log['message'][:50]}")
        
    except BlockingIOError:
        # Nadie está leyendo el FIFO, ignorar
        print(f"FIFO no tiene lector, alerta no enviada")
    except Exception as e:
        print(f"Error escribiendo en FIFO: {e}")
        raise

#    Tarea de health check para verificar que workers funcionan.

@celery_app.task(name='src.workers.tasks.health_check')
def health_check():
    
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


# Tarea periódica - limpiar logs viejos
@celery_app.task(name='src.workers.tasks.cleanup_old_logs')
def cleanup_old_logs(days=30):
    
    from datetime import datetime, timedelta
    from src.core.db import get_db_write
    
    cutoff_date = (datetime.now() - timedelta(days=days)).isoformat()
    
    with get_db_write() as conn:
        cursor = conn.cursor()
        
        # Contar logs a eliminar
        cursor.execute(
            "SELECT COUNT(*) FROM logs WHERE timestamp < ?",
            (cutoff_date,)
        )
        count = cursor.fetchone()[0]
        
        # Eliminar
        cursor.execute(
            "DELETE FROM logs WHERE timestamp < ?",
            (cutoff_date,)
        )
        
        return {
            'deleted': count,
            'cutoff_date': cutoff_date
        }
