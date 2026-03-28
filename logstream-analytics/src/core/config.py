# src/core/config.py
"""
Configuración centralizada de LogStream Analytics.

Todas las variables se leen desde el archivo .env en la raíz del proyecto.
Nunca hardcodear valores en otros módulos
"""

import os
from pathlib import Path
from dotenv import load_dotenv


# Buscar .env desde la raíz del proyecto 
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_ENV_PATH = _PROJECT_ROOT / '.env'

# Cargar variables de entorno
load_dotenv(_ENV_PATH)


def _get(key: str, default=None, cast=str):
    """
    Leer variable de entorno con cast de tipo y valor por defecto.

    """
    value = os.getenv(key)

    if value is None:
        if default is None:
            raise ValueError(
                f"Variable de entorno requerida no encontrada: '{key}'\n"
                f"Revisá tu archivo .env en: {_ENV_PATH}"
            )
        return default

    try:
        return cast(value)
    except (ValueError, TypeError) as e:
        raise ValueError(
            f"No se pudo convertir '{key}={value}' a {cast.__name__}: {e}"
        )


def _get_list(key: str, default: list = None, separator: str = ',') -> list:
    """Leer variable de entorno como lista separada por `separator`."""
    value = os.getenv(key)
    if value is None:
        return default if default is not None else []
    return [item.strip() for item in value.split(separator) if item.strip()]


class Config:
    """
    Clase que centraliza toda la configuración del proyecto.
    Se instancia una sola vez como singleton (`config`).
    """

    def __init__(self):
        # --- Redis ---
        self.REDIS_HOST: str                    = _get('REDIS_HOST', 'localhost')
        self.REDIS_PORT: int                    = _get('REDIS_PORT', 6379, int)
        self.REDIS_DB: int                      = _get('REDIS_DB', 0, int)
        self.REDIS_SOCKET_CONNECT_TIMEOUT: int  = _get('REDIS_SOCKET_CONNECT_TIMEOUT', 5, int)
        self.REDIS_SOCKET_TIMEOUT: int          = _get('REDIS_SOCKET_TIMEOUT', 5, int)
        self.REDIS_HEALTH_CHECK_INTERVAL: int   = _get('REDIS_HEALTH_CHECK_INTERVAL', 30, int)

        # --- Base de datos ---
        _db_path_raw                            = _get('DB_PATH', 'data/logstream.db')
        self.DB_PATH: Path                      = (
            Path(_db_path_raw) if Path(_db_path_raw).is_absolute()
            else _PROJECT_ROOT / _db_path_raw
        )
        self.DB_LOCK_TIMEOUT: int               = _get('DB_LOCK_TIMEOUT', 10, int)
        self.DB_LOCK_BLOCKING_TIMEOUT: int      = _get('DB_LOCK_BLOCKING_TIMEOUT', 15, int)

        # --- Log Server ---
        self.LOG_SERVER_HOST: str               = _get('LOG_SERVER_HOST', '::')
        self.LOG_SERVER_PORT: int               = _get('LOG_SERVER_PORT', 9000, int)

        # --- Query Engine ---
        self.QUERY_ENGINE_HOST: str             = _get('QUERY_ENGINE_HOST', '::')
        self.QUERY_ENGINE_PORT: int             = _get('QUERY_ENGINE_PORT', 9001, int)

        # --- Log Producer ---
        self.PRODUCER_DEFAULT_HOST: str         = _get('PRODUCER_DEFAULT_HOST', '127.0.0.1')
        self.PRODUCER_DEFAULT_PORT: int         = _get('PRODUCER_DEFAULT_PORT', 9000, int)
        self.PRODUCER_DEFAULT_RATE: int         = _get('PRODUCER_DEFAULT_RATE', 5, int)
        self.PRODUCER_DEFAULT_ERROR_RATE: float = _get('PRODUCER_DEFAULT_ERROR_RATE', 0.05, float)
        self.PRODUCER_DEFAULT_ANOMALY_RATE: float = _get('PRODUCER_DEFAULT_ANOMALY_RATE', 0.01, float)

        # --- Workers Celery ---
        self.CELERY_WORKER_PREFETCH_MULTIPLIER: int   = _get('CELERY_WORKER_PREFETCH_MULTIPLIER', 4, int)
        self.CELERY_WORKER_MAX_TASKS_PER_CHILD: int   = _get('CELERY_WORKER_MAX_TASKS_PER_CHILD', 1000, int)
        self.CELERY_TASK_TIME_LIMIT: int               = _get('CELERY_TASK_TIME_LIMIT', 300, int)
        self.CELERY_TASK_SOFT_TIME_LIMIT: int          = _get('CELERY_TASK_SOFT_TIME_LIMIT', 240, int)
        self.CELERY_RESULT_EXPIRES: int                = _get('CELERY_RESULT_EXPIRES', 3600, int)
        self.CELERY_TIMEZONE: str                      = _get('CELERY_TIMEZONE', 'America/Argentina/Mendoza')

        # --- Alert Manager — FIFO / comportamiento ---
        _fifo_raw                               = _get('FIFO_PATH', 'data/alert_pipe')
        self.FIFO_PATH: Path                    = (
            Path(_fifo_raw) if Path(_fifo_raw).is_absolute()
            else _PROJECT_ROOT / _fifo_raw
        )
        self.ALERT_LEVELS: list                 = _get_list('ALERT_LEVELS', ['ERROR', 'CRITICAL'])
        self.ALERT_STORE_IN_DB: bool            = _get('ALERT_STORE_IN_DB', 'true').lower() == 'true'
        self.ALERT_PRINT_TO_CONSOLE: bool       = _get('ALERT_PRINT_TO_CONSOLE', 'true').lower() == 'true'
        self.ALERT_EMAIL_ENABLED: bool          = _get('ALERT_EMAIL_ENABLED', 'false').lower() == 'true'
        # Niveles que disparan envío de mail (subconjunto de ALERT_LEVELS)
        self.ALERT_MAIL_LEVELS: list            = _get_list('ALERT_MAIL_LEVELS', ['CRITICAL'])
        # Intervalo en segundos para agrupar mails (0 = un mail por alerta)
        self.ALERT_MAIL_BATCH_SECONDS: int      = _get('ALERT_MAIL_BATCH_SECONDS', 0, int)
        # Pausa en segundos entre lecturas del FIFO cuando está vacío
        self.ALERT_FIFO_POLL_INTERVAL: float    = _get('ALERT_FIFO_POLL_INTERVAL', 0.5, float)

        # --- SMTP ---
        self.SMTP_HOST: str                     = _get('SMTP_HOST', 'localhost')
        self.SMTP_PORT: int                     = _get('SMTP_PORT', 587, int)
        self.SMTP_USER: str                     = _get('SMTP_USER', '')
        self.SMTP_PASSWORD: str                 = _get('SMTP_PASSWORD', '')
        self.SMTP_USE_TLS: bool                 = _get('SMTP_USE_TLS', 'true').lower() == 'true'
        self.ALERT_MAIL_FROM: str               = _get('ALERT_MAIL_FROM', '')
        # Lista de destinatarios separados por coma
        self.ALERT_MAIL_TO: list                = _get_list('ALERT_MAIL_TO', [])

        # --- General ---
        self.LOG_LEVEL: str                     = _get('LOG_LEVEL', 'INFO')
        self.PROJECT_ROOT: Path                 = _PROJECT_ROOT

    @property
    def REDIS_URL(self) -> str:
        """URL completa de conexión a Redis."""
        return f'redis://{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}'

    def __repr__(self) -> str:
        return (
            f"<Config "
            f"redis={self.REDIS_HOST}:{self.REDIS_PORT} "
            f"db={self.DB_PATH} "
            f"server={self.LOG_SERVER_HOST}:{self.LOG_SERVER_PORT}"
            f">"
        )


# Singleton 
config = Config()
