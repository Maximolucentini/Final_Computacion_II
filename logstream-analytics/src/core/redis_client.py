# src/core/redis_client.py
"""
Cliente Redis singleton para LogStream Analytics.
"""

import redis
from typing import Optional
from .config import config


# Cliente global (singleton)
_redis_client: Optional[redis.Redis] = None


def get_redis_client() -> redis.Redis:
    """
    Devolver cliente Redis (singleton).
    Crea la conexión la primera vez, reutiliza las siguientes.

    Returns:
        redis.Redis: Cliente conectado

    Raises:
        ConnectionError: Si no se puede conectar a Redis
    """
    global _redis_client

    if _redis_client is None:
        _redis_client = redis.Redis(
            host=config.REDIS_HOST,
            port=config.REDIS_PORT,
            db=config.REDIS_DB,
            decode_responses=False,
            socket_connect_timeout=config.REDIS_SOCKET_CONNECT_TIMEOUT,
            socket_timeout=config.REDIS_SOCKET_TIMEOUT,
            retry_on_timeout=True,
            health_check_interval=config.REDIS_HEALTH_CHECK_INTERVAL
        )

        try:
            _redis_client.ping()
        except redis.ConnectionError as e:
            _redis_client = None
            raise ConnectionError(
                f"No se pudo conectar a Redis "
                f"({config.REDIS_HOST}:{config.REDIS_PORT}): {e}"
            )

    return _redis_client


def reset_redis_client():
    """Cerrar y limpiar el cliente Redis (útil para tests)."""
    global _redis_client

    if _redis_client is not None:
        try:
            _redis_client.close()
        except Exception:
            pass
        _redis_client = None
