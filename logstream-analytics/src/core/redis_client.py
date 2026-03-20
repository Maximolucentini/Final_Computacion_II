# src/core/redis_client.py

import redis
from typing import Optional


# Cliente global (singleton)
_redis_client: Optional[redis.Redis] = None


def get_redis_client(host='localhost', port=6379, decode_responses=False):
   
    global _redis_client
    
    if _redis_client is None:
        _redis_client = redis.Redis(
            host=host,
            port=port,
            decode_responses=decode_responses,
            socket_connect_timeout=5,
            socket_timeout=5,
            retry_on_timeout=True,
            health_check_interval=30
        )
        
        # Verificar conexión
        try:
            _redis_client.ping()
        except redis.ConnectionError as e:
            _redis_client = None
            raise ConnectionError(f"No se pudo conectar a Redis: {e}")
    
    return _redis_client


def reset_redis_client():
    
    global _redis_client
    
    if _redis_client is not None:
        try:
            _redis_client.close()
        except Exception:
            pass
        _redis_client = None
